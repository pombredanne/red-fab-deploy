import os
from fabric.api import run, sudo, env
from fabric.context_managers import cd
from fabric.operations import get, put
from fabric.tasks import Task

import sgmllib
import urllib2

class PGBouncerInstall(Task):

    name = 'setup'

    pgbouncer_src = 'http://pkgsrc.smartos.org/packages/SmartOS/2012Q2/databases/pgbouncer-1.4.2.tgz'
    pkg_name = 'pgbouncer-1.4.2.tgz'

    def run(self):
        sudo('pkg_add libevent')
        sudo('pkg_add py27-psycopg2')

        with cd('/tmp'):
            run('wget %s' %self.pgbouncer_src)
            sudo('pkg_add %s' %self.pkg_name)

        sudo('mkdir -p /etc/pgbouncer')
        mkauth_script = os.path.join(env.configs_dir, 'mkauth.py')
        pgbouncer_config = os.path.join(env.configs_dir, 'pgbouncer.ini')
        svc_method = os.path.join(env.configs_dir, 'pgbouncer.xml')
        put(mkauth_script, '/etc/pgbouncer', use_sudo=True)
        put(pgbouncer_config, '/etc/pgbouncer', use_sudo=True)
        put(svc_method, '/etc/pgbouncer', use_sudo=True)

        with cd('/etc/pgbouncer'):
            sudo('python mkauth.py userlist.txt "user=postgres"')
        # postgres should be the owner of these config files
        sudo('chown -R postgres:postgres /etc/pgbouncer')

        # pgbouncer won't run smoothly without these directories
        sudo('mkdir -p /var/run/pgbouncer')
        sudo('mkdir -p /var/log/pgbouncer')
        sudo('chown postgres:postgres /var/run/pgbouncer')
        sudo('chown postgres:postgres /var/log/pgbouncer')

        # set up log
        sudo('logadm -C 3 -p1d -c -w /var/log/pgbouncer/pgbouncer.log -z 1')
        run('svccfg import /etc/pgbouncer/pgbouncer.xml')

        # start pgbouncer
        sudo('svcadm enable pgbouncer')

setup = PGBouncerInstall()
