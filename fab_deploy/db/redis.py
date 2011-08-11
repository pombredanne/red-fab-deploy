import fabric.api

from fab_deploy.file import link, unlink
from fab_deploy.package import package_install

def _redis_is_installed():
	with fabric.api.settings(fabric.api.hide('running','stdout','stderr'), warn_only=True):
		output = fabric.api.run('dpkg-query --show redis-server')
	return output.succeeded

def redis_install():
	""" Install redis-server. """
	if _redis_is_installed():
		fabric.api.warn(fabric.colors.yellow('Redis-server is already installed'))
		return

	package_install(['redis-server'])

def redis_setup(stage=''):
	""" Setup redis. """
	redis_file = '/etc/redis/redis.conf'
	if fabric.contrib.files.exists(redis_file):
		fabric.api.sudo('mv %s %s.bkp' % (redis_file,redis_file))
	if stage:
		stage = '.%s' % stage
	link('/srv/active/deploy/redis%s.conf' % stage, dest=redis_file,
		use_sudo=True, do_unlink=True, silent=True)

def redis_start():
	""" Start Nginx """
	fabric.api.run('redis-server')



