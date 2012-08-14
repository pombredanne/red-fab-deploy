import sys, os
from fabric.api import task, run, sudo, execute, env, local, settings
from fabric.tasks import Task
from fabric.contrib.files import append, sed, exists, contains
from fabric.operations import get, put
from fabric.context_managers import cd

from fab_deploy import functions

import utils

class BaseSetup(Task):
    """
    Base server setup.

    Installs ipfilter and adds firewall config

    Sets up ssh so root cannot login and other logins must
    be key based.
    """

    # Because setup tasks modify the config file
    # they should always be run serially.
    serial = True

    def _update_config(self, config_section):
        if not env.host_string:
            print "env.host_string is None, please specify a host by -H "
            sys.exit()
        added = False
        cons = env.config_object.get_list(config_section, env.config_object.CONNECTIONS)
        if not env.host_string in cons:
            added = True
            cons.append(env.host_string)
            env.config_object.set_list(config_section, env.config_object.CONNECTIONS,
                                        cons)


            ips = env.config_object.get_list(config_section, env.config_object.INTERNAL_IPS)
            internal_ip = run(utils.get_ip_command(None))
            ips.append(internal_ip)

            env.config_object.set_list(config_section, env.config_object.INTERNAL_IPS,
                                        ips)
        return added

    def _save_config(self):
        env.config_object.save(env.conf_filename)

    def _secure_ssh(self):
        # Change disable root and password
        # logins in /etc/ssh/sshd_config
        sudo('sed -ie "s/^PermitRootLogin.*/PermitRootLogin no/g" /etc/ssh/sshd_config')
        sudo('sed -ie "s/^PasswordAuthentication.*/PasswordAuthentication no/g" /etc/ssh/sshd_config')
        run('svcadm restart ssh')

    def _update_firewalls(self, config_section):
        # Generate the correct file
        execute('firewall.update_files', section=config_section)

        task = functions.get_task_instance('firewall.update_files')
        filename = task.get_section_path(config_section)
        execute('firewall.sync_single', filename=filename)

        # Update any section where this section appears
        for section in env.config_object.sections():
            if config_section in env.config_object.get_list(section,
                                                env.config_object.ALLOWED_SECTIONS):
                execute('firewall.update_files', section=section)

class LBSetup(BaseSetup):
    """
    Setup a load balancer

    After base setup installs nginx setups a git repo. Then
    calls the deploy task.

    Once finished it calls 'nginx.update_allowed_ips'

    This is a serial task as it modifies local config files.
    """

    name = 'lb_server'

    config_section = 'load-balancer'

    git_branch = 'master'
    git_hook = None

    nginx_conf = 'nginx/nginx-lb.conf'

    def _add_remote(self, name=None):
        if not env.host_string in env.git_reverse:
            name = functions.get_remote_name(env.host_string, self.config_section,
                                             name=name)
            execute('local.git.add_remote', remote_name=name,
                                    user_and_host=env.host_string)
        return name

    def _install_packages(self):
        pass

    def _modify_others(self):
        task = functions.get_task_instance('setup.app_server')
        execute('nginx.update_allowed_ips', nginx_conf=task.nginx_conf,
                            section=self.config_section)

    def _transfer_files(self):
        execute('git.setup', branch=self.git_branch, hook=self.git_hook)
        execute('local.git.push', branch=self.git_branch)


    def run(self, name=None):
        self._update_config()

        self._add_remote(name=name)

        # Transfer files first so all configs are in place.
        self._transfer_files()

        self._secure_ssh()
        self._install_packages()
        self._setup_services()
        self._update_firewalls(self.config_section)
        self._save_config()

        execute('deploy', branch=self.git_branch)

        self._modify_others()

    def _setup_services(self):
        execute('nginx.setup', nginx_conf=self.nginx_conf)
        run('svcadm enable nginx')

class AppSetup(LBSetup):
    """
    Setup a app-server

    Inherits from lb_setup so does everything it does.
    Also installs gunicorn, python, and other base packages.
    Runs the scripts/setup.sh script.

    Once finished it calls 'nginx.update_app_servers'

    This is a serial task as it modifies local config files.
    """

    name = 'app_server'

    config_section = 'app-server'

    nginx_conf = 'nginx/nginx.conf'

    def _modify_others(self):
        task = functions.get_task_instance('setup.lb_server')
        execute('nginx.update_app_servers', nginx_conf=task.nginx_conf,
                        section=self.config_section)

    def _install_packages(self):
        sudo('pkg_add python27')
        sudo('pkg_add py27-psycopg2')
        sudo('pkg_add py27-setuptools')
        sudo('easy_install-2.7 pip')
        self._install_venv()

    def _install_venv(self):
        sudo('pip install virtualenv')
        run('sh %s/scripts/setup.sh production' % env.git_working_dir)

    def _setup_services(self):
        super(AppSetup, self)._setup_services()
        execute('gunicorn.setup')
        run('svcadm enable gunicorn')

class DBSetup(BaseSetup):
    """
    Setup a database server
    """
    name = 'db_server'
    config_section = 'db-server'

    def run(self, name=None):
        self._update_config()
        self._secure_ssh()
        self._update_firewalls(self.config_section)
        dict = execute('postgres.master_setup', save_config=False)
        self._save_config()

class SlaveSetup(DBSetup):
    """
    Set up a slave database server with streaming replication
    """
    name = 'slave_db'
    config_section = 'slave-db'

    def _get_master(self):
        cons = env.config_object.get_list('db-server',
                                          env.config_object.CONNECTIONS)
        n = len(cons)
        if n == 0:
            print ('I could not find db server in server.ini.'
                   'Did you set up a master server?')
            sys.exit()
        else:
            for i in range(1, n+1):
                print "[%2d ]: %s" %(i, cons[i-1])
            while True:
                choice = raw_input('I found %d servers in server.ini.'
                                   'Which one do you want to use as master? ' %n)
                try:
                    choice = int(choice)
                    master = cons[choice-1]
                    break
                except:
                    print "please input a number between 1 and %d" %n-1

        return master

    def run(self, name=None):
        master = self._get_master()
        self._update_config()
        self._secure_ssh()
        self._update_firewalls(self.config_section)
        execute('postgres.slave_setup', master=master)
        self._save_config()

class DevSetup(AppSetup):
    """
    Setup a development server
    """
    name = 'dev_server'
    config_section = 'dev-server'

    def _modify_others(self):
        pass

    def _install_venv(self):
        sudo('pip install virtualenv')
        run('sh %s/scripts/setup.sh production development' % env.git_working_dir)

    def _setup_services(self):
        super(DevSetup, self)._setup_services()
        execute('postgres.master_setup')

app_server = AppSetup()
lb_server = LBSetup()
dev_server = DevSetup()
db_server = DBSetup()
slave_db = SlaveSetup()
