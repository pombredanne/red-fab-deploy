import fabric.api

def package_install(package, options = '', update = False):
	""" Installs packages via apt-get. """
	if update:
		fabric.api.warn('package_install(..., ..., update=True): Update feature is deprecated.  Just call package_update().') 
		package_update()
	if isinstance(package, (list, tuple)):
		package = " ".join(package)
	fabric.api.sudo('apt-get install --yes %s %s' % (options, package,))

def package_update():
	""" Update repositories on server """
	fabric.api.sudo('apt-get update --yes')

def package_upgrade():
	""" Upgrade all packages on the server """
	fabric.api.sudo('apt-get upgrade --yes')

def package_add_repository(repo):
	output = fabric.api.sudo('add-apt-repository %s' % repo)
	if 'not changed' in output:
		package_update()
	
def grab_from_web(href):
	with fabric.api.cd('/home/ubuntu'):
		fabric.api.run('wget %s' % href)
		filename = href.split('/')[-1]
		if '?' in filename:
			fabric.api.run('mv %s %s' % (filename, filename.split('?')[0]))
			filename = filename.split('?')[0]
		fabric.api.run('tar -xf %s' % filename)
		return filename.split('?')[0].strip('.tar.gz').strip('.tgz').strip('tar.bz2')

def compile_and_install(href, options=None):
	if options is None:
		options = ''
	dirname = grab_from_web(href)
	with fabric.api.cd('/home/ubuntu/%s' % dirname):
		fabric.api.run('./configure %s' % options)
		fabric.api.run('make')
		fabric.api.sudo('make install')