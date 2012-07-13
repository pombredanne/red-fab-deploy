import os

from fabric.api import env

from config import CustomConfig
from functions import gather_remotes

# Import all tasks
import local
from deploy import deploy

GIT_REPO_NAME = 'project-git'
GIT_WORKING_DIR = '/srv/active'

def setup_env(project_path):
    """
    Sets up the env settings for the fabric tasks

    Checks your git repo and adds your remotes as
    aliases for those hosts. Letting you do -H web1,web2
    when you have web1 and web2 in your remotes

    Creates roles out of each section in the config file.
    Letting you do -R app-servers and that command will
    be passed to all app servers.

    Provides access to some variables that can be used through
    tasks.

        env.deploy_path: the local location of the deploy folder
        env.project_path: the local location of the root of your project
        env.git_repo_name: the remote name of the git repo.
        env.git_working_dir: the remote path where the code should be deployed

        env.config_object: The servers.ini file loaded by the config parser
        env.conf_filename: The path to the servers.ini file

        env.git_remotes: A mapping of git remote names to hosts
        env.git_reverse: The reverse of above
    """

    # Setup fabric env
    env.deploy_path = os.path.join(project_path, 'deploy')
    env.project_path = project_path
    env.git_repo_name = GIT_REPO_NAME
    env.git_working_dir = GIT_WORKING_DIR

    BASE = os.path.abspath(os.path.dirname(__file__))
    env.configs_dir = os.path.join(BASE, 'default-configs')

    # Read the config and store it in env
    config = CustomConfig()
    env.conf_filename = os.path.abspath(os.path.join(project_path, 'deploy', 'servers.ini'))
    config.read([ env.conf_filename ])
    env.config_object = config

    # Add sections to the roledefs
    for section in config.sections():
        if config.has_option(section, CustomConfig.CONNECTIONS):
            env.roledefs[section] = config.get_list(section, CustomConfig.CONNECTIONS)

    env.git_remotes = gather_remotes()
    env.git_reverse = dict([(v, k) for (k, v) in env.git_remotes.iteritems()])

    # Translate any known git names to hosts
    hosts = []
    for host in env.hosts:
        if host in env.git_remotes:
            host = env.git_remotes[host]
        hosts.append(host)
    env.hosts = hosts
