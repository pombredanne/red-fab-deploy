from fabric.api import local, env, execute
from fabric.tasks import Task

class AddGitRemote(Task):
    """
    Adds a remote to your git repo.

    Requires two arguments:
        remote_name: The name this remote should have in your repo.
        user_and_host: The connection string for this remote. admin@10.0.1.1
                       for example. This should not include the path to the
                       repo

    This is a serial task, that should not be called
    with any remote hosts as it performs no remote actions.

    """

    name = 'add_remote'
    serial = True

    def run(self, remote_name=None, user_and_host=None):
        if not remote_name:
            raise Exception("You must provide a name for the new remote")

        ssh_path = "ssh://%s/~/%s" % (user_and_host, env.git_repo_name)
        local('git remote add %s %s' % (remote_name, ssh_path))

class RemoveGitRemote(Task):
    """
    Removes a remote from your git repo.

    Requires one argument:
        remote_name: The name that you want to remove from your git repo.

    This is a serial task, that should not be called
    with any remote hosts as it performs no remote actions.
    """

    name = 'rm_remote'
    serial = True

    def run(self, remote_name=None):
        local('git remote rm %s' % remote_name)

class GitPush(Task):
    """
    Pushes your repo to remotes specified by hosts

    Takes one optional argument:
        branch: The branch that you would like to push.
                If it is not provided 'master' will be used.

    Will raise an error if a specified host isn't in your git
    remotes.
    """

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
