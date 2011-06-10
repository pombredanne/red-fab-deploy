import fabric.api

from fab_deploy.file import link
from fab_deploy.package import package_update, package_install
from fab_deploy.utils import detect_os

#--- Java Tools
def _java_is_installed():
	with fabric.api.settings(fabric.api.hide('running','stdout','stderr'), warn_only=True):
		output = fabric.api.run('dpkg-query --show sun-java6-jdk')
		return output.succeeded

def java_install():
	""" 
	Install Sun Java6 
	
	Currently it is recommended you do these on the server directly.  
	Fabric has trouble with the prompts that you must answer during
	installation.
	"""
	if _java_is_installed():
		fabric.api.warn(fabric.colors.yellow('Sun Java6 JDK is already installed'))
		return

	if detect_os() == 'maverick':
		fabric.api.sudo('add-apt-repository "deb http://archive.canonical.com/ lucid partner"')
		package_update()
	package_install(['sun-java6-jdk','sun-java6-jre',])

# --- SmarfoxServerPro Commands

SFS_VERSION = 'SFS_PRO_1.6.6'
SFS_PROGRAM = '/srv/%s/Server/sfs' % (SFS_VERSION)

def _sfs_is_installed():
	if fabric.contrib.files.exists(SFS_PROGRAM):
		return True
	return False

def sfs_install():
	""" Install SmartFoxServer Pro v.1.6.6 """

	if not _java_is_installed():
		fabric.api.warn(fabric.colors.yellow('Sun Java6 JDK must be installed'))
		return
	
	if _sfs_is_installed():
		fabric.api.warn(fabric.colors.yellow('SmartFoxServer Pro is already installed'))
		return

	# Get SmartFoxServer Pro
	sfs_filename = 'SFSPRO_linux64_1.6.6'
	with fabric.api.cd('/srv'):
		fabric.api.run('wget http://www.smartfoxserver.com/products/download.php?d=77 -O %s.tar.gz' % sfs_filename)
		fabric.api.run('gzip -d %s.tar.gz' % sfs_filename)
		fabric.api.run('tar xf %s.tar'     % sfs_filename)
	
	# Install SmartFoxServer Pro
	with fabric.api.cd('/srv/SmartFoxServer_PRO_1.6.6'):
		fabric.api.run('./install')
	
	# Install the 64-bit wrapper
	with fabric.api.cd('/srv'):
		fabric.api.run('wget http://www.smartfoxserver.com/download/wrapper/wrapper_linux64.zip')
		package_install(['unzip'],"--no-install-recommends")
		fabric.api.run('cp linux64/libwrapper.so  /srv/%s/Server/lib' % (SFS_VERSION))
		fabric.api.run('cp linux64/wrapper.jar    /srv/%s/Server/lib' % (SFS_VERSION))
		fabric.api.run('cp linux64/wrapper        /srv/%s/Server/wrapper_64'  % (SFS_VERSION))
		fabric.api.run('mv /srv/%s/Server/wrapper /srv/%s/Server/wrapper_32'  % (SFS_VERSION))
		link('/srv/%s/Server/wrapper_64' % (SFS_VERSION),dest='/srv/%s/Server/wrapper' % (SFS_VERSION))

def sfs_setup():
	""" Setup SmartFoxPro Server """
	# Link the config file
	sfs_config = '/srv/%s/Server/config.xml' % (SFS_VERSION)
	if fabric.contrib.files.exists(sfs_config):
		fabric.api.run('mv %s %s.bkp' % (sfs_config, sfs_config))
	link('/srv/active/deploy/config.xml',dest=sfs_config,do_unlink=True,silent=True)
	
	# Make smartfox a startup process
	link(SFS_PROGRAM, dest='/etc/rc2.d/S99sfs',use_sudo=True,do_unlink=True,silent=True)

def sfs_service(command):
	if not _sfs_is_installed():
		fabric.api.warn(fabric.colors.yellow('SmartFoxServer Pro must be installed'))
		return
	
	fabric.api.run('%s %s' % (SFS_PROGRAM,command))
	sfs_message(command)

def sfs_start():   sfs_service('start')
def sfs_stop():    sfs_service('stop')
def sfs_restart(): sfs_service('restart')
def sfs_status():  sfs_service('status')
def sfs_message(message): 
	""" Print a smartfox message """
	fabric.api.puts(fabric.colors.green('smartfox %s for %s' % (message,fabric.api.env['host_string'])))
