from fabric.api import local, env, execute
from fabric.tasks import Task

class AddGitRemote(Task):
    name = 'add_remote'

    def run(self, remote_name=None, user_and_host=None):
        if not remote_name:
            raise Exception("You must provide a name for the new remote")

        ssh_path = "ssh://%s/~/%s" % (user_and_host, env.git_repo_name)
        local('git remote add %s %s' % (remote_name, ssh_path))

class RemoveGitRemote(Task):
    name = 'rm_remote'

    def run(self, remote_name=None):
        local('git remote rm %s' % remote_name)

class GitPush(Task):
    name = 'push'

    def run(self, branch=None, hosts=[]):
        if not branch:
           branch = 'master'

        remote_name = env.git_reverse[env.host_string]
        local('git push %s %s' % (
                remote_name, branch))


push = GitPush()
add_remote = AddGitRemote()
rm_remote = RemoveGitRemote()
