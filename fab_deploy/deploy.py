from fab_deploy import vcs
from fab_deploy.conf import fab_config, import_string
from fab_deploy.db import *
from fab_deploy.file import link, unlink, link_exists
from fab_deploy.machine import get_provider_dict, stage_exists, ec2_create_key, ec2_authorize_port, deploy_instances, update_instances
from fab_deploy.server import *
from fab_deploy.server.s3fs import s3fs_install, s3fs_setup
from fab_deploy.system import get_hostname, set_hostname, prepare_server
from fab_deploy.virtualenv import pip_install, virtualenv_create
from tempfile import mkdtemp
import fabric.api
import fabric.colors
import fabric.contrib
import os.path
import time


def go(stage="development", key_name='ec2.development'):
	""" 
	A convenience method to prepare AWS servers.
	
	Use this to create keys, authorize ports, and deploy instances.
	DO NOT use this step if you've already created keys and opened
	ports on your ec2 instance.
	"""

	# Setup keys and authorize ports
	ec2_create_key(key_name)
	ec2_authorize_port('default','tcp','22')
	ec2_authorize_port('default','tcp','80')

	# Deploy the instances for the given stage
	deploy_instances(stage,key_name)
	update_instances()

def go_setup(stage="development"):
	"""
	Install the correct services on each machine
	
    $ fab -i deploy/[your private SSH key here] set_hosts go_setup
	"""
	stage_exists(stage)
	PROVIDER = get_provider_dict()

	# Determine if a master/slave relationship exists for databases in config
	slave = []
	for db in ['mysql','postgresql','postgresql-client']:
		slave.append(any(['slave' in PROVIDER['machines'][stage][name].get('services',{}).get(db,{}) for name in PROVIDER['machines'][stage]]))
	replication = any(slave)
	# Begin installing and setting up services
	for name in PROVIDER['machines'][stage]:
		node_data = PROVIDER['machines'][stage][name]
		address = node_data['public_ip'][0]
		if address == fabric.api.env.host:
			set_hostname(name)
			prepare_server()
			install_services(node_data['id'], name, address, stage, node_data, replication=replication)
			import_string(node_data.get('post_setup'))()

def install_services(id, name, address, stage, node_data, **kwargs):
	''' Install all services '''
	
	for service in node_data['services']:
		settings = node_data['services'][service]
		if service == 'nginx':
			nginx_install()
			nginx_setup(stage, settings)
		elif service == 'uwsgi':
			uwsgi_install()
			uwsgi_setup(stage, settings)
		elif service == 'mysql':
			mysql_install()
			mysql_setup(stage=stage,replication=kwargs.get('replication'),**settings)
		elif service == 'postgresql':
			postgresql_install(id, name, address, stage, settings, **kwargs)
			postgresql_setup(id, name, address, stage, settings, **kwargs)
		elif service == 'postgresql-client':
			postgresql_client_install(id, name, address, stage, settings, **kwargs)
		elif service == 'pgpool':
			pgpool_install(id, name, address, stage, settings, **kwargs)
		elif service == 's3fs':
			s3fs_install(id, name, address, stage, settings, **kwargs)
			s3fs_setup(id, name, address, stage, settings, **kwargs)
		elif service in ['apache']:
			fabric.api.warn(fabric.colors.yellow("%s is not yet available" % service))
		else:
			fabric.api.warn(fabric.colors.yellow('%s is not an available service' % service))

def go_deploy(stage="development", tagname="trunk", username="ubuntu", use_existing=False):
	"""
	Deploy project and make active on any machine with server software
	
    $ fab -i deploy/[your private SSH key here] set_hosts go_deploy
	"""
	stage_exists(stage)
	PROVIDER = get_provider_dict()
	for name in PROVIDER['machines'][stage]:
		instance_dict = PROVIDER['machines'][stage][name]
		host = instance_dict['public_ip'][0]

		if host == fabric.api.env.host:
			service = instance_dict['services']
			# If any of these services are listed then deploy the project
			if list(set(['nginx','uwsgi','apache']) & set(instance_dict['services'])):
				deploy_full(tagname,force=True,username=username, use_existing=use_existing)
	
def deploy_full(tagname, force=False, username="ubuntu", use_existing=False):
	""" 
	Deploys a project with a given tag name, and then makes
	that deployment the active deployment on the server.
	"""
	deploy_project(tagname,force=force,username=username,use_existing=use_existing)
	make_active(tagname)

def deploy_project(tagname, force=False, username="ubuntu", use_existing=False, with_full_virtualenv=True):
	""" Deploys project on prepared server. """
	make_src_dir(username=username)
	tag_dir = os.path.join(fabric.api.env.conf['SRC_DIR'], tagname)
	if fabric.contrib.files.exists(tag_dir):
		if force:
			fabric.api.warn(fabric.colors.yellow('Removing directory %s and all its contents.' % tag_dir))
			fabric.api.run('rm -rf %s' % tag_dir)
		elif not use_existing:
			fabric.api.abort(fabric.colors.red('Tagged directory already exists: %s' % tagname))
	#fabric.api.local('rm -rf %s' % os.path.join('/tmp', tagname))
	tempdir = mkdtemp()
	with fabric.api.lcd(mkdtemp()):
		vcs.export(tagname, local=True)
		fabric.contrib.project.rsync_project(
			local_dir = tagname,
			remote_dir = fabric.api.env.conf['SRC_DIR'],
			exclude = fabric.api.env.conf['RSYNC_EXCLUDE'], 
			extra_opts='--links --perms')
		fabric.api.local('rm -rf %s' % os.path.join(tagname))

	virtualenv_create(dir = tag_dir)
	if with_full_virtualenv:
		pip_install(dir = tag_dir)
	
	fabric.api.sudo('chown -R %s:%s /srv' % (username,username))
	#fabric.api.env.conf.post_activate.get(data['server-type'], lambda: None)() #TODO #XXX

def make_src_dir(username='ubuntu'):
	""" Makes the /srv/<project>/ directory and creates the correct permissions """
	fabric.api.sudo('mkdir -p %s' % (fabric.api.env.conf['SRC_DIR']))
	fabric.api.sudo('chown -R %s:%s /srv' % (username,username))

def make_active(tagname):
	""" Make a tag at /srv/<project>/<tagname>  active """
	link(os.path.join(fabric.api.env.conf['SRC_DIR'], tagname),
			'/srv/active', do_unlink=True, silent=True)

def check_active():
	""" Abort if there is no active deployment """
	if not link_exists('/srv/active/'):
		fabric.api.abort(fabric.colors.red('There is no active deployment'))

def undeploy():
	""" Shuts site down. This command doesn't clean everything, e.g.
	user data (database, backups) is preserved. """

	if not fabric.contrib.console.confirm("Do you wish to undeploy host %s?" % fabric.api.env.hosts[0], default=False):
		fabric.api.abort(fabric.colors.red("Aborting."))

	web_server_stop()
	unlink('/srv/active')

