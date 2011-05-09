import fabric.api
import fabric.contrib

from fab_deploy.file import link, unlink
from fab_deploy.package import package_install
from fab_deploy.system import service

def _apache_is_installed():
	with fabric.api.settings(fabric.api.hide('running','stdout','stderr'), warn_only=True):
		output = fabric.api.run('dpkg-query --show apache2')
	return output.succeeded

def apache_install():
	""" Installs apache. """
	package_install(['apache2','libapache2-mod-wsgi','libapache2-mod-rpaf'])
	run('rm -f /etc/apache2/sites-enabled/default')
	run('rm -f /etc/apache2/sites-enabled/000-default')
	apache_setup_locale()

def apache_setup_locale():
	""" Setups apache locale. Apache is unable to handle file uploads with
	unicode file names without this. """
	fabric.contrib.files.append('/etc/apache2/envvars', [
			'export LANG="en_US.UTF-8"', 'export LC_ALL="en_US.UTF-8"'])

def apache_setup(stage=''):
	""" Setup apache. """
	apache_file = '/etc/apache2/httpd.conf'
	if fabric.contrib.files.exists(apache_file):
		fabric.api.sudo('mv %s %s.bkp' % (apache_file,apache_file))
	if stage:
		stage = '.%s' % stage
	link('/srv/active/deploy/httpd%s.conf' % stage, dest=apache_file,
		use_sudo=True, do_unlink=True, silent=True)

def apache_service(command):
	""" Run an apache service """
	if not _apache_is_installed():
		fabric.api.warn(fabric.colors.yellow('Apache must be installed'))
		return

	service('apache2',command)
	apache_message(command)

def apache_start():
	""" Starts apache using init.d script. """
	apache_service('start')

def apache_stop():
	""" Stops apache using init.d script. """
	apache_service('stop')

def apache_restart():
	""" Restarts apache using init.d script. """
	apache_service('restart')

def apache_message(message):
	""" Print an apache message """
	fabric.api.puts(fabric.colors.green('apache2 %s for %s' % (message,fabric.api.env['host_string'])))

