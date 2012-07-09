from fabric.api import local, env, execute, task
from fabric.decorators import runs_once

@runs_once
def pre_deploy(branch=None):
    execute('local.deploy.prep', branch=branch)

@task(hosts=[])
def deploy(branch=None):
    pre_deploy(branch=branch)
    execute('local.deploy.do', branch=branch)
