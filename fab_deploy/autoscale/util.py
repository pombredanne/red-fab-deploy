from fab_deploy.virtualenv import virtualenv
from fabric.api import cd, run, put
from fabric.contrib.files import exists

def update_fab_deploy(fabfile = None, config = None):
    ''' Updates fab_deploy (only) on server.  Useful for debugging'''
    if exists('/srv/active'):
        with cd('/srv/active/'):
            run('ls env || virtualenv env')
            with virtualenv():
                run('pip install -e git+git://github.com/daveisaacson/red-fab-deploy.git#egg=fab_deploy')
        if fabfile:
            put(fabfile, '/srv/active/fabfile.py')
        if config:
            put(config, '/srv/active/%s' % config)
