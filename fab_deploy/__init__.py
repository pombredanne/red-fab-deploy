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
