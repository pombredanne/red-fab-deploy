from fabric.api import local, env, execute
from fabric.tasks import Task
from fabric.context_managers import settings, hide

class Deploy(Task):
    """
    Deploys your project.

    Takes one optional argument:
        branch: The branch that you would like to push.
                If it is not provided 'master' will be used.


    This rsync's your collected-static directory with the remote
    then executes 'local.git.push'.
    """

    cache_prefix = 'c-'
    name = 'do'

    def _sync_files(self, branch):
        """
        Sync collected static, make sure remote links with
        the self.cache_prefix aren't deleted.
        """

        local('rsync -rptv --progress --delete-after --filter "P %s" %s/collected-static/ %s:%s/collected-static' % (self.cache_prefix, env.project_path, env.host_string, env.git_working_dir))
        execute('local.git.push', branch=branch)

    def _post_sync(self):
        """
        Hook that is executed after a git push.
        """
        pass

    def run(self, branch=None):
        if not branch:
            branch = 'master'

        self._sync_files(branch)
        self._post_sync()

class PrepDeploy(Task):
    """
    Preps your static files for deployment.

    Takes one optional argument:
        branch: The branch that you would like to push.
                If it is not provided 'master' will be used.


    Internally this stashes any changes you have, checks out the
    requested branch, runs rake tasks for css/js and then the
    django command collected static.

    If anything was stashed in the beginning it trys to restore it.

    This is a serial task, that should not be called directly
    with any remote hosts as it performs no remote actions.
    """

    serial = True
    stash_name = 'deploy_stash'
    name = 'prep'

    def _clean_working_dir(self, branch):
        # Force a checkout
        local('git stash save %s' % self.stash_name)
        local('git checkout %s' % branch)

    def _prep_static(self):
        local('rake dev:compass')
        local('rake dev:uglify')
        local('%s/env/bin/python %s/project/manage.py collectstatic --noinput' % (env.project_path, env.project_path))

    def _restore_working_dir(self):
        with settings(warn_only=True):
            with hide('running', 'warnings'):
                # Fail if there was no stash by this name
                result = local('git stash list stash@{0} | grep %s' % self.stash_name )

            if not result.failed:
                local('git stash pop')

    def run(self, branch=None):

        if not branch:
            branch = 'master'

        self._clean_working_dir(branch)
        self._prep_static()
        self._restore_working_dir()

do = Deploy()
prep_deploy = PrepDeploy()
