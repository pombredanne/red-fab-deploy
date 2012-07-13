from fabric.api import local, env, execute, task
from fabric.decorators import runs_once

@runs_once
def pre_deploy(branch=None):
    """
    Make sure that local.deploy.prep is only run
    once when the deploy command is run on multiple
    hosts.
    """

    execute('local.deploy.prep', branch=branch)

@task(hosts=[])
def deploy(branch=None):
    """
    Deploy this project.

    Internally calls local.deploy.prep once and then
    local.deploy.do for each host.

    Takes an optional branch argument that can be used
    to deploy a branch other than master.
    """

    pre_deploy(branch=branch)
    execute('local.deploy.do', branch=branch)
