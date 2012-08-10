import os
from time import sleep
from cStringIO import StringIO
from fabric.api import run, sudo, env, hide, local
from fabric.context_managers import cd
from fabric.operations import get, put
from fabric.tasks import Task

import sgmllib
import urllib2

class PGBouncerInstall(Task):

    name = 'setup'

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

    def _get_all_passwd(self):
        with hide('output'):
            string = run('sudo su postgres -c \'psql -c "select usename, '
                         'passwd from pg_shadow order by 1"\'')
        f = StringIO(string)
        f.readline()
        f.readline()
        lines = []
        for line in f.readlines():
            list = line.split('|')
            if len(list) >= 2:
                user = list[0].strip()
                passwd = list[1].strip()
                lines.append('"%s" "%s" ""\n' %(user, passwd))

        out = open('/tmp/userlist.txt', 'w')
        out.write("".join(lines))
        out.close()
        put('/tmp/userlist.txt', '%s/pgbouncer.userlist' %self.config_dir, use_sudo=True)
        local('rm /tmp/userlist.txt')

    def run(self):
        sudo('pkg_add libevent')
        sudo('pkg_add py27-psycopg2')
        sudo('mkdir -p /opt/pkg/bin')
        sudo("ln -sf /opt/local/bin/awk /opt/pkg/bin/nawk")
        sudo("ln -sf /opt/local/bin/sed /opt/pkg/bin/nbsed")

        with cd('/tmp'):
            run('wget %s' %self.pgbouncer_src)
            sudo('pkg_add %s' %self.pkg_name)

        svc_method = os.path.join(env.configs_dir, 'pgbouncer.xml')
        put(svc_method, self.config_dir, use_sudo=True)

        self._setup_parameter('%s/pgbouncer.ini' %self.config_dir, **self.config)
        self._get_all_passwd()
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

setup = PGBouncerInstall()
