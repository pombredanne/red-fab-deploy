import fabric.api

from fab_deploy.package import package_install, package_add_repository

def _nodejs_nodejs():
	with fabric.api.settings(fabric.api.hide('running','stdout','stderr'), warn_only=True):
		output = fabric.api.run('dpkg-query --show nodejs')
	return output.succeeded

def nodejs_install():
	""" Install nodejs. """
	if _nodejs_nodejs():
		fabric.api.warn(fabric.colors.yellow('nodejs is already installed'))
		return
	package_add_repository('ppa:chris-lea/node.js')
	package_install(['python-software-properties', 'nodejs'])
	fabric.api.sudo('curl http://npmjs.org/install.sh | sudo sh')

def nodejs_setup():
	""" Setup nodejs."""
	pass

def nodejs_start():
	""" Start nodejs."""
	pass


