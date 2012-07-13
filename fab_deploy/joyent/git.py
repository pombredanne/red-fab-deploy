import os

from fabric.api import run, sudo, env, put, execute
from fabric.tasks import Task
from fabric.context_managers import settings, hide

from fab_deploy.functions import get_config_filepath

DEFAULT_GIT_HOOK = 'git/post-receive'

class Install(Task):
    """
    Setup a remote git repo

    Installs git and creates a repo using env.git_repo_name
    for the location.
    """
    name = 'setup'

    def run(self, branch=None, hook=None, hosts=[]):
        self._install_package()
        self._setup_dirs()
        execute('git.update_hook', hook=hook)

    def _install_package(self):
        sudo("pkg_add scmgit")

    def _setup_dirs(self):
        with settings(hide('running', 'warnings'), warn_only=True):
            run("rm -rf %s" % env.git_repo_name)

        sudo('mkdir -p %s' % env.git_working_dir)
        user=run('whoami')
        sudo('chown -R %s %s' % (user, env.git_working_dir))
        run('git init --bare %s' % env.git_repo_name)

class UpdateHook(Task):
    """
    Update the post-receive hook

    Copy a post-receive hook to the remote server and make
    sure it is executable.

    Takes an optional argument:
        hook: Path to the hook you want installed. If not
              given the default git/post-receive is used.
    """

    name = 'update_hook'

    def run(self, hook=None):
        file_path = get_config_filepath(hook, DEFAULT_GIT_HOOK)
        path = os.path.join(env.git_repo_name, "hooks", "post-receive")
        put(file_path, path)
        run('chmod +x %s' % path)

setup = Install()
update_hook = UpdateHook()
