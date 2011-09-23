import fabric.api
from fab_deploy.conf import fab_config

def get_vcs():
	""" Returns a module with current VCS """
	name = fab_config.get('vcs')
	return __import__(name, globals(), fromlist=name.split('.')[1:])

def init():
	get_vcs().init()

def up(tagname,local=False):
	""" Runs vcs ``update`` command on server """
	get_vcs().up(tagname,local)

def push(tagname,local=False):
	""" Runs vcs ``checkout`` command on server """
	get_vcs().push(tagname,local)

def export(tagname,local=False):
	""" Runs vcs ``export`` command on server """
	get_vcs().export(tagname,local)

def configure():
	get_vcs().configure()

