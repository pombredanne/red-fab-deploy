from fabric.api import local, env, execute
from fabric.tasks import Task
from fabric.context_managers import settings, hide

class Deploy(Task):
    cache_prefix = 'c-'
    name = 'do'

    def _sync_files(self, branch):
        local('rsync -rptv --progress --delete-after --filter "P %s" %s/collected-static/ %s:%s/collected-static' % (self.cache_prefix, env.project_path, env.host_string, env.git_working_dir))
        execute('local.git.push', branch=branch)

    def _post_sync(self):
        pass

    def run(self, branch=None):
        if not branch:
            branch = 'master'

        self._sync_files(branch)
        self._post_sync()

class PrepDeploy(Task):
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
