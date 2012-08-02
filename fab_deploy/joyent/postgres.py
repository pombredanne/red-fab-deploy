import os
import sys

from fabric.api import run, sudo, env, local
from fabric.contrib.files import append, sed, exists, contains
from fabric.context_managers import prefix
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


setup = PostgresInstall()