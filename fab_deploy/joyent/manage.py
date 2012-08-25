from fabric.api import execute, env
from fabric.tasks import Task

from fab_deploy import functions

class FirewallSync(Task):
    """
    Updates the firewall on a live server.

    Calls 'firewall.update_files' and then updates the
    remote servers using 'firewall.sync_single'

    Takes the same arguments as 'firewall.update_files

    While this task will deploy any changes it makes they
    are not commited to your repo. You should review any
    changes and commit as appropriate.
    """

    name = 'firewall_sync'
    serial = True

    def run(self, section=None):
        execute('firewall.update_files', section=section)
        if section:
            sections = [section]
        else:
            sections = env.config_object.sections()

        task = functions.get_task_instance('firewall.update_files')
        for s in sections:
            filename = task.get_section_path(s)
            execute('firewall.sync_single', filename=filename,
                hosts=env.config_object.get_list(section,
                                env.config_object.CONNECTIONS))

firewall_sync = FirewallSync()
