import sys, os
from time import sleep
from uuid import uuid4
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

    def _check_hosts(self):
        if env.host_string:
            self._update_config(self.config_section)
        else:
            print "env.host_string is None, please specify a host by -H "
            sys.exit()

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
        self._check_hosts()

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

    def run(self):
        self._check_hosts()
        self._secure_ssh()
        self._update_firewalls(self.config_section)
        self._save_config()
        execute('postgres.setup')

class ReplicationSetup(BaseSetup):
    """
    Set up master-slave streaming replication: slave node
    """

    name = 'db_slave'

    def _get_data_dir(self, db_version):
        return os.path.join('/var', 'pgsql', 'data%s' %db_version)

    def _get_master_db_version(self, master):
        command = ("ssh %s psql --version | head -1 | awk '{print $3}'" %master)
        version_string = local(command, capture=True)
        version = ''.join(version_string.split('.')[:2])

        return version

    def _setup_parameter(self, file, **kwargs):
        for key, value in kwargs.items():
            origin = "#%s =" %key
            new = "%s = %s" %(key, value)
            sudo('sed -i "/%s/ c\%s" %s' %(origin, new, file))

    def _setup_archive_dir(self, data_dir):
        archive_dir = os.path.join(data_dir, 'wal_archive')
        sudo("mkdir -p %s" %archive_dir)
        sudo("chown postgres:postgres %s" %archive_dir)

    def _setup_recovery_conf(self, master_ip, password, data_dir):
        wal_dir = os.path.join(data_dir, 'wal_archive')
        recovery_conf = os.path.join(data_dir, 'recovery.conf')

        txts = (("standby_mode = 'on'\n") +
                ("primary_conninfo = 'host=%s " %master_ip) +
                    ("port=5432 user=replicator password=%s'\n" %password) +
                ("trigger_file = '/tmp/pgsql.trigger'\n") +
                ("restore_command = 'cp -f %s/%s </dev/null'\n"
                    %(wal_dir, '%f %p')) +
                ("archive_cleanup_command = 'pg_archivecleanup %s %s'\n"
                    %(wal_dir, "%r")))

        sudo('touch %s' %recovery_conf)
        append(recovery_conf, txts, use_sudo=True)
        sudo('chown postgres:postgres %s' %recovery_conf)

    def _setup_postgres_config(self, data_dir, config):
        postgres_conf = os.path.join(data_dir, 'postgresql.conf')

        if exists(postgres_conf, use_sudo=True):
            self._setup_parameter(postgres_conf, **config)
        else:
            print ('Could not find %s' %postgres_conf)
            sys.exit()

    def _setup_hba_config(self, data_dir, hba_txt):
        hba_conf= os.path.join(data_dir, 'pg_hba.conf')
        append(hba_conf, hba_txt, use_sudo=True)

    def _ssh_key_exchange(self, master, slave, data_dir):
        rsa_file = os.path.join('/tmp', 'id_rsa')
        pub_rsa = os.path.join('/tmp', 'id_rsa.pub')
        local('ssh-keygen -t rsa -f %s -N ""' %rsa_file)

        for host in [master, slave]:
            with settings(host_string=host):
                ssh_dir = '/var/pgsql/.ssh'
                sudo('mkdir -p %s' %ssh_dir)
                with cd(ssh_dir):
                    put(rsa_file, 'id_rsa', use_sudo=True)
                    put(pub_rsa, 'id_rsa.pub', use_sudo=True)
                    sudo('cat %s > authorized_keys'
                         %os.path.join(ssh_dir, 'id_rsa.pub'))
                    sudo('chown -R postgres:postgres %s' %ssh_dir)
                    sudo('chmod -R og-rwx %s' %ssh_dir)

        local('rm %s %s' %(rsa_file, pub_rsa))

    def run(self):
        cons = env.config_object.get_list('db-server',
                                          env.config_object.CONNECTIONS)
        if len(cons) > 1:
            print ('Sorry, there are two db-servers in server.ini, and I don\'t'
                   'know how to setup two master servers')
            sys.exit()
        elif len(cons) < 1:
            print ('I could not find db server in server.ini.'
                   'Did you set up db server?')
            sys.exit()
        else:
            master = cons[0]
            master_ip = master.split('@')[1]

        db_version = self._get_master_db_version(master=master)
        data_dir = self._get_data_dir(db_version)
        slave = env.host_string
        slave_ip = slave.split('@')[1]
        replicator_pass = uuid4().hex

        # execute('postgres.setup',db_version=db_version) #this or next one?
        sudo("pkg_add postgresql%s-server" %data_dir)
        sudo("pkg_add postgresql%s-replicationtools" %data_dir)
        sudo('svcadm enable postgresql:pg%s' %db_version) #initilize
        sudo('svcadm disable postgresql:pg%s' %db_version)

        self._ssh_key_exchange(master, slave, data_dir)

        with settings(host_string=master):
            sudo('svcadm disable postgresql:pg%s' %db_version)
            self._setup_archive_dir(data_dir)

            c1 = ('CREATE USER replicator REPLICATION LOGIN ENCRYPTED PASSWORD \'%s\';'
                  %replicator_pass)
            run('psql -U postgres -c "%s"' %c1)

            hba_txt = 'host\treplication\treplicator\t%s/32\tmd5' %slave_ip
            config = {'wal_level': 'hot_standby',
                      'wal_keep_segments': '32',
                      'max_wal_senders':   '5',
                      'archive_mode':      'on',
                      'archive_command':   '\'cp %s %s/wal_archive/%s\'' %('%p', data_dir, '%f')}
            self._setup_postgres_config(data_dir=data_dir, config=config)
            self._setup_hba_config(data_dir=data_dir, hba_txt=hba_txt)

            sudo('svcadm enable postgresql:pg%s' %db_version)
            sleep(1) # to make sure the server is really started

            run('psql -U postgres -c "SELECT pg_start_backup(\'backup\', true)"')
            run('sudo su - postgres -c "rsync -av --exclude postmaster.pid --exclude pg_xlog %s/ postgres@%s:%s/"' %(data_dir, slave_ip, data_dir))
            run('psql -U postgres -c "SELECT pg_stop_backup()"')

        config = {'wal_level':      'hot_standby',
                  'hot_standby':    'on',}
        self._setup_postgres_config(data_dir=data_dir, config=config)
        self._setup_archive_dir(data_dir)
        self._setup_recovery_conf(master_ip=master_ip,
                                  password=replicator_pass, data_dir=data_dir)
        hba_txt = ('host\treplication\treplicator\t%s/32\tmd5\n'
                   'host\treplication\treplicator\t%s/32\tmd5'
                   %(slave_ip,master_ip))
        self._setup_hba_config(data_dir=data_dir, hba_txt=hba_txt)
        sudo('svcadm enable postgresql:pg%s' %db_version)

        print('password for replicator on master is %s' %replicator_pass)


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
        execute('postgres.setup')

app_server = AppSetup()
lb_server = LBSetup()
dev_server = DevSetup()
db_server = DBSetup()
db_slave = ReplicationSetup()
