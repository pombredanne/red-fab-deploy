from fabric.api import local, env, execute
from fabric.tasks import Task

from fab_deploy.functions import get_answer, get_remote_name

class InternalIps(Task):
    name = 'update_internal_ips'
    serial = True

    def run(self):
        conf = env.config_object
        for section in conf.sections():
            internals = conf.get_list(section, conf.INTERNAL_IPS)
            connections = conf.get_list(section, conf.CONNECTIONS)
            if len(internals) != len(connections):
                raise Exception("Number of connections and internal ips do not match")

            if internals:
                results = execute('utils.get_ip', None, hosts=connections)
                for i, conn in enumerate(connections):
                    internals[i] = results[conn]

                conf.set_list(section, conf.INTERNAL_IPS, internals)
                conf.save(env.conf_filename)

class SyncGit(Task):
    name = 'sync_git'
    default = True
    serial = True

    def gather_config_remotes(self):
        config_remotes = {}
        conf = env.config_object

        for section in conf.sections():
            if conf.has_option(section, conf.GIT_SYNC) and conf.getboolean(section, conf.GIT_SYNC):
                for c in conf.get_list(section, conf.CONNECTIONS):
                    config_remotes[c] = section
        return config_remotes

    def run(self):
        config_remotes = self.gather_config_remotes()

        to_delete = []
        to_add = [ x for x in config_remotes.keys() if not x in env.git_reverse ]

        for value, name in env.git_reverse.items():
            if name == 'origin':
                continue

            if not value in config_remotes:
                test = get_answer("The remote %s %s isn't in your servers.ini. Do you want to remove it?" %(name, value))
                if test:
                    to_delete.append(name)

        for name in to_delete:
            execute('local.git.rm_remote', remote_name=name)

        for value in to_add:
            name = get_remote_name(value, config_remotes[value])
            execute('local.git.add_remote', remote_name=name,
                                user_and_host=value)

sync_git = SyncGit()
update_internal_ips = InternalIps()
