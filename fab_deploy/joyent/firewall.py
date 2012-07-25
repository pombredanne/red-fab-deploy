import os

from fab_deploy import functions

from fabric.api import run, sudo, env, put, execute, local
from fabric.tasks import Task

DEFAULT_CONF_FILE = 'ipf/ipf.conf'

class FirewallSingleSync(Task):
    """
    Sync a ipf config file

    Takes one required argument:
        filename: the full path to the file to sync.
    """

    name = 'sync_single'

    def run(self, filename=None):
        assert filename

        put(filename, '/var/tmp/tmpipf.conf')
        sudo("mv /var/tmp/tmpipf.conf /etc/ipf/ipf.conf")
        run('svccfg -s ipfilter:default setprop firewall_config_default/policy = astring: "custom"')
        run('svccfg -s ipfilter:default setprop firewall_config_default/custom_policy_file = astring: "/etc/ipf/ipf.conf"')
        run('svcadm refresh ipfilter:default')
        run('svcadm enable ipfilter')
        run('svcadm restart ipfilter')

class FirewallUpdate(Task):
    """
    Update ipf config file(s)

    Takes one argument:
        section: The name of the section in your server.ini that you
                 would like to update. If section is not provided all
                 sections will be updated.

    Changes made by this task are not commited to your repo, or deployed
    anywhere automatically. You should review any changes and commit and
    deploy as appropriate.

    This is a serial task, that should not be called directly
    with any remote hosts as it performs no remote actions.
    """

    name = 'update_files'
    serial = True

    # IP Filter Defaults
    IPF_RESTRICTED_LINE = "pass in quick on net1 proto tcp from %s to any port = %s keep state group 200"
    IPF_OPEN_LINE = "pass in quick proto tcp from any to any port = %s keep state group 200"

    START_DELM = "## Start Configurable Section ##"
    END_DELM = "## End Configurable Section ##"

    def _get_project_config_filepath(self, section):
        return "ipf/%s.conf" % section

    def get_section_path(self, section):

        file_path = functions.get_config_filepath(
                        self._get_project_config_filepath(section),
                        DEFAULT_CONF_FILE
        )

        if not os.path.exists(file_path):
            path = os.path.dirname(file_path)
            local('mkdir -p %s' % path)

            org = os.path.join(env.configs_dir, 'ipf.conf')
            local('cp %s %s' % (org, file_path))

        return file_path

    def _get_config_text(self, section, conf):
        txt = [self.START_DELM]
        for port in conf.get_list(section, conf.OPEN_PORTS):
            txt.append(self.IPF_OPEN_LINE % port)

        # If we have restricted ports
        restricted_ports = conf.get_list(section, conf.RESTRICTED_PORTS)
        if restricted_ports:
            # Get all the internals
            internals = []
            for section in conf.get_list(section, conf.ALLOWED_SECTIONS):
                internals.extend(conf.get_list(section, conf.INTERNAL_IPS))

            # Add a line for each port
            for internal in internals:
                for port in restricted_ports:
                    txt.append(self.IPF_RESTRICTED_LINE % (internal, port))

        if len(txt) > 1:
            txt.append(self.END_DELM)
            return '\\n'.join(txt)

    def _save_to_file(self, section, text):
        file_path = self.get_section_path(section)

        new_path = file_path + '.bak'
        cmd = "awk '{\
               if ($0==\"%s\") { \
                    print \"%s\"; \
                    while(getline>0){if ($0==\"%s\") break;} \
                    next;} \
                {print $0}}' %s > %s" %(self.START_DELM, text, self.END_DELM,
                                        file_path, new_path)
        local(cmd)
        local('mv %s %s' %(new_path, file_path))
        return file_path

    def run(self, section=None):

        if section:
            sections = [section]
        else:
            execute('local.config.update_internal_ips')
            sections = env.config_object.sections()

        for s in sections:
            text = self._get_config_text(s, env.config_object)
            self._save_to_file(s, text)

update_files = FirewallUpdate()
sync_single = FirewallSingleSync()
