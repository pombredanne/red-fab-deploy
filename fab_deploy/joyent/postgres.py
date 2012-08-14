import os
import sys
import sgmllib
import urllib2
import tempfile

from fabric.api import run, sudo, env, local, hide
from fabric.contrib.files import append, sed, exists, contains
from fabric.context_managers import prefix, cd
from fabric.operations import get, put
from fabric.tasks import Task

class PostgresInstall(Task):
    """
    Install postgresql on server

    install postgresql package;
    enable postgres access from localhost without password;
    enable all other user access from other machines with password;
    database server listen to all machines '*';
    create a user for database with password.
    """

    name = 'setup'
    db_version = '9.1'
    encrypt = 'md5'
    hba_txts = ('local   all    postgres                     trust\n'
                'local   all    all                          password\n'
                '# # IPv4 local connections:\n'
                'host    all    all         127.0.0.1/32     %(encrypt)s\n'
                '# # IPv6 local connections:\n'
                'host    all    all         ::1/128          %(encrypt)s\n'
                '# # IPv4 external\n'
                'host    all    all         0.0.0.0/0        %(encrypt)s\n')

    def run(self, db_version=None, encrypt=None, *args, **kwargs):

        if not db_version:
            db_version = self.db_version
        db_version = ''.join(db_version.split('.')[:2])
        data_dir = self._get_data_dir(db_version)

        if not encrypt:
            encrypt = self.encrypt

        self._install_package(db_version=db_version)
        self._setup_hba_config(data_dir, encrypt)
        self._setup_postgres_config(data_dir)

        self._restart_db_server(db_version)
        self._create_user()

    def _get_data_dir(self, db_version):
        return os.path.join('/var', 'pgsql', 'data%s' %db_version)

    def _install_package(self, db_version=None):
        pkg = 'postgresql%s-server' %db_version
        sudo("pkg_add %s" %pkg)
        sudo("svcadm enable postgresql:pg%s" %db_version)

    def _setup_hba_config(self, data_dir=None, encrypt=None):
        """ enable postgres access without password from localhost"""

        hba_conf = os.path.join(data_dir, 'pg_hba.conf')
        kwargs = {'data_dir':data_dir, 'encrypt':encrypt}
        hba_txts = self.hba_txts % kwargs

        if exists(hba_conf, use_sudo=True):
            sudo("echo '%s' > %s" %(hba_txts, hba_conf))
        else:
            print ('Could not find file %s. Please make sure postgresql was '
                   'installed and data dir was created correctly.'%hba_conf)
            sys.exit()

    def _setup_postgres_config(self, data_dir=None):
        """ enable password-protected access for all user from all remotes """
        postgres_conf = os.path.join(data_dir, 'postgresql.conf')

        if exists(postgres_conf, use_sudo=True):
            from_str = "#listen_addresses = 'localhost'"
            to_str = "listen_addresses = '*'"
            sudo('sed -i "s/%s/%s/g" %s' %(from_str, to_str, postgres_conf))
        else:
            print ('Could not find file %s. Please make sure postgresql was '
                   'installed and data dir was created correctly.' %postgres_conf)
            sys.exit()

    def _restart_db_server(self, db_version):
        sudo('svcadm restart postgresql:pg%s' %db_version)

    def _create_user(self):
        username = raw_input("Nowe we are creating a database user, please "
                             "specify a username: ")
        # 'postgres' is postgresql superuser
        while username == 'postgres':
            username = raw_input("Sorry, you are not allowed to use postgres "
                                 "as username, please choose another one: ")
        run("sudo su postgres -c 'createuser -D -S -R -P %s'" %username)


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
setup_pgbouncer = PGBouncerInstall()
