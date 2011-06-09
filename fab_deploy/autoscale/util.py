from fab_deploy.autoscale.hosts import set_hosts
from fab_deploy.conf import fab_config, fab_data
from fab_deploy.virtualenv import virtualenv
from fabric.context_managers import cd
from fabric.decorators import runs_once
from fabric.operations import put, run
from fabric.state import env
import fabric.contrib.files

def update_fab_deploy(fabfile = None):
    ''' Updates fab_deploy (only) on server.  Useful for debugging'''
    if fabric.contrib.files.exists('/srv/active'):
        with cd('/srv/active/'):
            run('ls env || virtualenv env')
            with virtualenv():
                run('pip install -e git+git://github.com/daveisaacson/red-fab-deploy.git#egg=fab_deploy')
        if fabfile:
            put(fabfile, '/srv/active/fabfile.py')

