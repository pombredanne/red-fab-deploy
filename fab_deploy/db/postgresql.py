from datetime import datetime
import time, os

import fabric.api, fabric.contrib.files

from fab_deploy.package import package_install, package_add_repository, compile_and_install
from fab_deploy.machine import get_provider_dict,get_connection
from fab_deploy.system import service
from fab_deploy.utils import append

def _postgresql_is_installed():
	with fabric.api.settings(fabric.api.hide('stderr'), warn_only=True):
		output = fabric.api.run('postgres --version')
	return output.succeeded

def _postgresql_client_is_installed():
	with fabric.api.settings(fabric.api.hide('stderr'), warn_only=True):
		output = fabric.api.run('psql --version')
	return output.succeeded

def _pgpool_is_installed():
	with fabric.api.settings(fabric.api.hide('stderr'), warn_only=True):
		output = fabric.api.run('pgpool --version')
	return output.succeeded

def postgresql_install(id, name, address, stage, options, replication=False, master = None):
	""" Installs postgreSQL """

	if _postgresql_is_installed():
		fabric.api.warn(fabric.colors.yellow('PostgreSQL is already installed.'))
		return
	
	config = get_provider_dict()
	if master is None and 'slave' in options and 'name' not in options: # name in options means autoscale, I guess?
		master_conf = config['machines'][stage][options['slave']]
		options.update(master_conf['services']['postgresql'])
		master = master_conf['public_ip'][0]
	
	package_add_repository('ppa:pitti/postgresql')
	package_install(['postgresql', 'python-psycopg2'])
	
	# Figure out cluster name
	output = fabric.api.run('pg_lsclusters -h')
	if output:
		version, cluster = output.split()[:2]
	else:
		version = fabric.api.run('pg_dump --version').split()[-1]
		cluster = 'main'
	
	if options.get('ebs_size'):
		package_install('xfsprogs')
		package_install('mdadm', '--no-install-recommends')
		
		# Create two ebs volumes
		import boto.ec2 #TODO: factor out ec2 stuffs
		ec2 = boto.ec2.connect_to_region(config['location'][:-1],
							aws_access_key_id = fabric.api.env.conf['AWS_ACCESS_KEY_ID'],
							aws_secret_access_key = fabric.api.env.conf['AWS_SECRET_ACCESS_KEY'])
		
		tag1 = u'%s-1' % name
		tag2 = u'%s-2' % name
		if not any(vol for vol in ec2.get_all_volumes() if vol.tags.get(u'Name') == tag1):
			volume1 = ec2.create_volume(options.get('ebs_size', 10)/2, config['location'])
			volume1.add_tag('Name', tag1)
			volume1.attach(id, '/dev/sdf')
		if not any(vol for vol in ec2.get_all_volumes() if vol.tags.get(u'Name') == tag2):
			volume2 = ec2.create_volume(options.get('ebs_size', 10)/2, config['location'])
			volume2.add_tag('Name', tag2)
			volume2.attach(id, '/dev/sdg')
		
		time.sleep(10)
		
		# RAID 0 together the EBS volumes, and format the result as xfs.  Mount at /data.
		if not fabric.contrib.files.exists('/dev/md0', True):
			fabric.api.sudo('mdadm --create /dev/md0 --level=0 --raid-devices=2 /dev/sdf /dev/sdg')
			fabric.api.sudo('mkfs.xfs /dev/md0')
		
		# Add mountpoint
		if not fabric.contrib.files.exists('/data'):
			fabric.api.sudo('mkdir -p /data')
			fabric.api.sudo('chown postgres:postgres /data')
			fabric.api.sudo('chmod 644 /data')
		
		# Add to fstab and mount
		append('/etc/fstab', '/dev/md0  /data  auto  defaults  0  0', True)
		with fabric.api.settings(warn_only = True):
			fabric.api.sudo('mount /data')
			
	else:
		if not fabric.contrib.files.exists('/data'):
			fabric.api.sudo('mkdir -p /data')
			fabric.api.sudo('chown postgres:postgres /data')
			fabric.api.sudo('chmod 644 /data')
	
	# Move cluster/dbs to /data
	if fabric.api.run('pg_lsclusters -h').split()[5] != '/data':
		fabric.api.sudo('pg_dropcluster --stop %s %s' % (version, cluster))
		fabric.api.sudo('pg_createcluster --start -d /data -e UTF-8 %s %s' % (version, cluster))

	fabric.api.sudo('service postgresql stop')

	# Set up postgres config files - Allow global listening (have a firewall!) and local ubuntu->your user connections
	pg_dir = '/etc/postgresql/%s/%s/' % (version, cluster)
	fabric.contrib.files.comment(pg_dir + 'postgresql.conf', 'listen_addresses', True)
	append(pg_dir + 'postgresql.conf', "listen_addresses = '*'", True)

	fabric.contrib.files.sed(pg_dir + 'pg_hba.conf', "ident", "trust", use_sudo=True)
	
	# Figure out if we're a master
	if replication and 'slave' not in options:
		# We're a master!
		
		append(pg_dir + 'postgresql.conf', [
			'wal_level = hot_standby',
			'max_wal_senders = 1',
			'checkpoint_segments = 8',
			'wal_keep_segments = 8'], True)
		
		append(pg_dir + 'pg_hba.conf', "host replication all 0.0.0.0/0 md5", True)
		
	elif 'slave' in options:
		# We're a slave!
		
		append(pg_dir + 'postgresql.conf', [
			'hot_standby = on',
			'checkpoint_segments = 8',
			'wal_keep_segments = 8'], True)
		
		#fabric.api.sudo('rm -rf /data/*')
		append('/data/recovery.conf', [
			"standby_mode = 'on'",
			"primary_conninfo = 'host=%s port=5432 user=%s password=%s'" % (master, options['user'], options['password']),
			"trigger_file = '/data/failover'"], True)
		
		ssh_master = 'ssh -i %s ubuntu@%s' % (fabric.api.env.key_filename[0], master)
		ssh_slave = 'ssh -i %s ubuntu@%s' % (fabric.api.env.key_filename[0], address)
		
		fabric.api.local('%s echo' % ssh_master) # To make sure warnings are cleared
		fabric.api.local('%s echo' % ssh_slave) # To make sure warnings are cleared
		
		fabric.api.local('%s sudo tar czvf - /data | %s sudo tar xzvf - -C /' % (ssh_master, ssh_slave))
		fabric.api.sudo('chown -R postgres:postgres /data')
		#XXX: create user nobody? don't need to create users on both i suppose
	if options.get('support_pgpool'):
		if 'nobody' not in fabric.api.sudo('''su postgres -c "psql -c '\du'"'''):
			fabric.api.sudo('su postgres -c "createuser -DIRS -U postgres -P nobody"' % (options['user']))
		append(pg_dir + 'pg_hba.conf', ['host postgres nobody 0.0.0.0/0 trust', #TODO: see if pgpool can send a password with health check somehow
										'hostssl all all 0.0.0.0/0 password'], True)
	else:
		append(pg_dir + 'pg_hba.conf', "host all all 0.0.0.0/0 md5", True)
	
	fabric.api.sudo('service postgresql start')
	
def postgresql_client_install(id, name, address, stage, options, **kwargs):
	if _postgresql_client_is_installed():
		fabric.api.warn(fabric.colors.yellow('The PostgreSQL client is already installed.'))
		return
	
	package_add_repository('ppa:pitti/postgresql')
	package_install(['postgresql-client', 'python-psycopg2'])
	
def postgresql_setup(id, name, address, stage, options, **kwargs):
	if 'slave' not in options:
		with fabric.api.settings(warn_only = True):
			if options['user'] not in fabric.api.sudo('''su postgres -c "psql -c '\du'"'''):
				fabric.api.sudo('su postgres -c "createuser -s -U postgres -P %s"' % (options['user']))
			if options['name'] not in fabric.api.sudo('''su postgres -c "psql -c '\l'"'''):
				fabric.api.sudo('su postgres -c "createdb -U %s %s"' % (options['user'], options['name']))

def pgpool_install(id, name, address, stage, options, **kwargs):
	if _pgpool_is_installed():
		fabric.api.warn(fabric.colors.yellow('pgpool is already installed.'))
		return
	
	with fabric.api.settings(warn_only = True):
		fabric.api.sudo('service pgpool stop')

	package_install('libpq-dev')
	compile_and_install('http://pgfoundry.org/frs/download.php/2958/pgpool-II-3.0.3.tar.gz', '--with-openssl --sysconfdir=/etc')
	fabric.api.put(os.path.join(fabric.api.env.conf['FILES'], 'pgpool.conf'), '/etc/pgpool.conf', use_sudo=True)
	
	# Add user for health check
	append('/etc/pcp.conf', 'pgpool:%s' % fabric.api.run('pg_md5 %s' % options['password']), True)
	
	# Service script
	service_script = '/etc/init.d/pgpool'
	if fabric.contrib.files.exists(service_script):
		fabric.api.sudo('mv %s %s.bkp' % (service_script, service_script))
	fabric.api.put(os.path.join(fabric.api.env.conf['FILES'], 'pgpool_init.sh'), service_script, use_sudo=True)
	fabric.api.sudo('chmod 755 %s' % service_script)
	fabric.api.sudo('chown root:root %s' % service_script)
	fabric.api.sudo('update-rc.d -f pgpool defaults')

	fabric.api.sudo('mkdir -p /var/log/pgpool')
	#fabric.api.sudo('pgpool -c -f /etc/pgpool.conf')
	fabric.api.sudo('service pgpool start')

def pgpool_set_hosts(*hosts):
	fabric.contrib.files.comment('/etc/pgpool.conf', 'backend_hostname', True)	
	for i, slave in enumerate(hosts):
		append('/etc/pgpool.conf', ['backend_hostname%d = %s' % (i, slave.public_dns_name),
									'backend_port%d = 5432' % i,
									'backend_weight%d = 1' % i], use_sudo=True)
	fabric.api.sudo('service pgpool restart') #TODO: reload isn't working for some reason
