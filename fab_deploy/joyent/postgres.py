import os
import sys
import sgmllib
import urllib2
import tempfile

from fabric.api import run, sudo, env, local, hide, settings
from fabric.contrib.files import append, sed, exists, contains
from fabric.context_managers import prefix
from fabric.operations import get, put
from fabric.context_managers import cd

from fabric.tasks import Task

from utils import random_password

class PostgresInstall(Task):
    """
    Install postgresql on server

    install postgresql package;
    enable postgres access from localhost without password;
    enable all other user access from other machines with password;
    setup a few parameters related with streaming replication;
    database server listen to all machines '*';
    create a user for database with password.
    """

    name = 'master_setup'
    db_version = '9.1'

    encrypt = 'md5'
    hba_txts = ('local   all    postgres                     ident\n'
                'host    replication replicator  0.0.0.0/0   md5\n'
                'local   all    all                          password\n'
                '# # IPv4 local connections:\n'
                'host    all    all         127.0.0.1/32     %(encrypt)s\n'
                '# # IPv6 local connections:\n'
                'host    all    all         ::1/128          %(encrypt)s\n'
                '# # IPv4 external\n'
                'host    all    all         0.0.0.0/0        %(encrypt)s\n')

    postgres_config = {
        'listen_addresses':  "'*'",
        'wal_level':         "hot_standby",
        'wal_keep_segments': "32",
        'max_wal_senders':   "5",
        'archive_mode':      "on" }

    def _get_data_dir(self, db_version):
        return os.path.join('/var', 'pgsql', 'data%s' %db_version)

    def _setup_parameter(self, file, **kwargs):
        for key, value in kwargs.items():
            origin = "#%s =" %key
            new = "%s = %s" %(key, value)
            sudo('sed -i "/%s/ c\%s" %s' %(origin, new, file))

    def _install_package(self, db_version=None):
        sudo("pkg_add postgresql%s-server" %db_version)
        sudo("pkg_add postgresql%s-replicationtools" %db_version)
        sudo("svcadm enable postgresql:pg%s" %db_version)

    def _setup_hba_config(self, data_dir=None, encrypt=None):
        """
        enable postgres access without password from localhost
        """
        hba_conf = os.path.join(data_dir, 'pg_hba.conf')
        kwargs = {'data_dir':data_dir, 'encrypt':encrypt}
        hba_txts = self.hba_txts % kwargs

        if exists(hba_conf, use_sudo=True):
            sudo("echo '%s' > %s" %(hba_txts, hba_conf))
        else:
            print ('Could not find file %s. Please make sure postgresql was '
                   'installed and data dir was created correctly.'%hba_conf)
            sys.exit()

    def _setup_postgres_config(self, data_dir=None, config=None):
        postgres_conf = os.path.join(data_dir, 'postgresql.conf')

        if exists(postgres_conf, use_sudo=True):
            self._setup_parameter(postgres_conf, **config)
        else:
            print ('Could not find file %s. Please make sure postgresql was '
                   'installed and data dir was created correctly.' %postgres_conf)
            sys.exit()

    def _setup_archive_dir(self, data_dir):
        archive_dir = os.path.join(data_dir, 'wal_archive')
        sudo("mkdir -p %s" %archive_dir)
        sudo("chown postgres:postgres %s" %archive_dir)

        return archive_dir

    def _setup_ssh_key(self):
        ssh_dir = '/var/pgsql/.ssh'

        sudo('mkdir -p %s' %ssh_dir)
        sudo('chown -R postgres:postgres %s' %ssh_dir)
        sudo('chmod -R og-rwx %s' %ssh_dir)
        rsa = os.path.join(ssh_dir, 'id_rsa')
        run('sudo su postgres -c "ssh-keygen -t rsa -f %s -N \'\'"' %rsa)

    def _restart_db_server(self, db_version):
        sudo('svcadm restart postgresql:pg%s' %db_version)

    def _create_user(self):
        username = raw_input("Now we are creating the database user, please "
                             "specify a username: ")
        # 'postgres' is postgresql superuser
        while username == 'postgres':
            username = raw_input("Sorry, you are not allowed to use postgres "
                                 "as username, please choose another one: ")
        db_out = run('echo "select usename from pg_shadow where usename=\'%s\'" |'
                     'sudo su postgres -c psql' %username)
        if username in db_out:
            print 'user %s already exists, skipping creating user.' %username
        else:
            run("sudo su postgres -c 'createuser -D -S -R -P %s'" %username)

        env.config_object.set('db-server', env.config_object.USERNAME, username)

        return username

    def _create_replicator(self, db_version):
        db_out = run("echo '\du replicator' | sudo su postgres -c 'psql'")
        if 'replicator' not in db_out:
            replicator_pass = random_password(12)

            c1 = ('CREATE USER replicator REPLICATION LOGIN ENCRYPTED '
                  'PASSWORD \"\'%s\'\"' %replicator_pass)
            run("echo %s | sudo su postgres -c \'psql\'" %c1)
            history_file = os.path.join('/var', 'pgsql', '.psql_history')
            if exists(history_file):
                sudo('rm %s' %history_file)
            print "user replicator already exists, skipping creating user."

            env.config_object.set('db-server', env.config_object.REPLICATOR,
                                  'replicator')
            env.config_object.set('db-server', env.config_object.REPLICATOR_PASS,
                                  replicator_pass)

            return replicator_pass

    def run(self, db_version=None, encrypt=None, save_config=True, **kwargs):
        if not db_version:
            db_version = self.db_version
        db_version = ''.join(db_version.split('.')[:2])
        data_dir = self._get_data_dir(db_version)
        hba_conf= os.path.join(data_dir, 'pg_hba.conf')

        if not encrypt:
            encrypt = self.encrypt

        self._install_package(db_version=db_version)
        archive_dir = self._setup_archive_dir(data_dir)
        self.postgres_config['archive_command'] = ("'cp %s %s/wal_archive/%s'"
                                                   %('%p', data_dir, '%f'))

        self._setup_hba_config(data_dir, encrypt)
        self._setup_postgres_config(data_dir=data_dir,
                                    config=self.postgres_config)
        self._restart_db_server(db_version)
        self._setup_ssh_key()
        self._create_user()
        self._create_replicator(db_version)

        if save_config:
            env.config_object.save(env.conf_filename)


class SlaveSetup(PostgresInstall):
    """
    Set up master-slave streaming replication: slave node
    """

    name = 'slave_setup'

    postgres_config = {
        'listen_addresses': "'*'",
        'wal_level':      "hot_standby",
        'hot_standby':    "on"}

    def _get_master_db_version(self, master):
        command = ("ssh %s psql --version | head -1 | awk '{print $3}'" %master)
        version_string = local(command, capture=True)
        version = ''.join(version_string.split('.')[:2])

        return version

    def _get_replicator_pass(self, section='db-server'):
        password = env.config_object.get_list(section,
                                             env.config_object.REPLICATOR_PASS)
        return password[0]

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

    def _ssh_key_exchange(self, master, slave):
        """
        copy ssh key(pub) from master to slave, so that master can access slave
        without password via ssh
        """
        ssh_dir = '/var/pgsql/.ssh'

        with settings(host_string=master):
            rsa_pub = os.path.join(ssh_dir, 'id_rsa.pub')
            with hide('output'):
                pub_key = sudo('cat %s' %rsa_pub)

        with settings(host_string=slave):
            authorized_keys = os.path.join(ssh_dir, 'authorized_keys')
            with hide('output', 'running'):
                run('sudo su postgres -c "echo %s >> %s"'
                    %(pub_key, authorized_keys))

    def run(self, master=None, encrypt=None, **kwargs):
        if not master:
            print "Hey, a master is required for slave."
            sys.exit()

        master_ip = master.split('@')[-1]
        db_version = self._get_master_db_version(master=master)
        data_dir = self._get_data_dir(db_version)
        slave = env.host_string
        slave_ip = slave.split('@')[1]
        hba_conf= os.path.join(data_dir, 'pg_hba.conf')

        self._install_package(db_version=db_version)
        sudo('svcadm disable postgresql:pg%s' %db_version)

        self._setup_ssh_key()
        self._ssh_key_exchange(master, slave)

        with settings(host_string=master):

            run('echo "select pg_start_backup(\'backup\', true)" | sudo su postgres -c \'psql\'')
            run('sudo su postgres -c "rsync -av --exclude postmaster.pid '
                '--exclude pg_xlog %s/ postgres@%s:%s/"'%(data_dir, slave_ip, data_dir))
            run('echo "select pg_stop_backup()" | sudo su postgres -c \'psql\'')

        self._setup_postgres_config(data_dir=data_dir,
                                    config=self.postgres_config)
        self._setup_archive_dir(data_dir)

        replicator_pass = self._get_replicator_pass()
        self._setup_recovery_conf(master_ip=master_ip,
                                  password=replicator_pass, data_dir=data_dir)

        if not encrypt:
            encrypt = self.encrypt
        self._setup_hba_config(data_dir, encrypt)

        sudo('svcadm enable postgresql:pg%s' %db_version)
        print('password for replicator on master node is %s' %replicator_pass)

class PGBouncerInstall(Task):
    """
    Set up PGBouncer on a database server
    """

    name = 'setup_pgbouncer'

    pgbouncer_src = 'http://pkgsrc.smartos.org/packages/SmartOS/2012Q2/databases/pgbouncer-1.4.2.tgz'
    pkg_name = 'pgbouncer-1.4.2.tgz'
    config_dir = '/etc/opt/pkg'

    config = {
        '*':              'host=127.0.0.1',
        'logfile':        '/var/log/pgbouncer/pgbouncer.log',
        'pidfile':        '/var/run/pgbouncer/pgbouncer.pid',
        'listen_addr':    '*',
        'listen_port':    '6432',
        'unix_socket_dir': '/tmp',
        'auth_type':      'md5',
        'auth_file':      '%s/pgbouncer.userlist' %config_dir,
        'pool_mode':      'session',
        'admin_users':    'postgres',
        'stats_users':    'postgres',
        }

    def _setup_parameter(self, file, **kwargs):
        for key, value in kwargs.items():
            origin = "%s =" %key
            new = "%s = %s" %(key, value)
            sudo('sed -i "/%s/ c\%s" %s' %(origin, new, file))

    def _get_passwd(self, username):
        with hide('output'):
            string = run('echo "select usename, passwd from pg_shadow where '
                         'usename=\'%s\' order by 1" | sudo su postgres -c '
                         '"psql"' %username)

        user, passwd = string.split('\n')[2].split('|')
        user = user.strip()
        passwd = passwd.strip()

        __, tmp_name = tempfile.mkstemp()
        fn = open(tmp_name, 'w')
        fn.write('"%s" "%s" ""\n' %(user, passwd))
        fn.close()
        put(tmp_name, '%s/pgbouncer.userlist'%self.config_dir, use_sudo=True)
        local('rm %s' %tmp_name)

    def _get_username(self, section=None):
        try:
            names = env.config_object.get_list(section, env.config_object.USERNAME)
            username = names[0]
        except:
            print ('You must first set up a database server on this machine, '
                   'and create a database user')
            raise
        return username

    def run(self, section=None):

        sudo('pkg_add libevent')
        sudo('mkdir -p /opt/pkg/bin')
        sudo("ln -sf /opt/local/bin/awk /opt/pkg/bin/nawk")
        sudo("ln -sf /opt/local/bin/sed /opt/pkg/bin/nbsed")

        with cd('/tmp'):
            run('wget %s' %self.pgbouncer_src)
            sudo('pkg_add %s' %self.pkg_name)

        svc_method = os.path.join(env.configs_dir, 'pgbouncer.xml')
        put(svc_method, self.config_dir, use_sudo=True)

        self._setup_parameter('%s/pgbouncer.ini' %self.config_dir, **self.config)

        if not section:
            section = 'db-server'
        username = self._get_username(section)
        self._get_passwd(username)
        # postgres should be the owner of these config files
        sudo('chown -R postgres:postgres %s' %self.config_dir)

        # pgbouncer won't run smoothly without these directories
        sudo('mkdir -p /var/run/pgbouncer')
        sudo('mkdir -p /var/log/pgbouncer')
        sudo('chown postgres:postgres /var/run/pgbouncer')
        sudo('chown postgres:postgres /var/log/pgbouncer')

        # set up log
        sudo('logadm -C 3 -p1d -c -w /var/log/pgbouncer/pgbouncer.log -z 1')
        run('svccfg import %s/pgbouncer.xml' %self.config_dir)

        # start pgbouncer
        sudo('svcadm enable pgbouncer')

setup = PostgresInstall()
slave_setup = SlaveSetup()
setup_pgbouncer = PGBouncerInstall()
