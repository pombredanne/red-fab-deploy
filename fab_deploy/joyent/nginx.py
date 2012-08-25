import os

from fabric.api import run, sudo, env, local
from fabric.tasks import Task

DEFAULT_NGINX_CONF = "nginx/nginx.conf"

class NginxInstall(Task):
    """
    Install nginx

    Takes one optional argument:
        nginx_conf: the relative path of the nginx config file
                    (that is part of your repo) that you want use
                    as your nginx config. If not provided it will
                    default to nginx/nginx.conf

    Also sets up log rotation
    """

    name = 'setup'

    def run(self, nginx_conf=None, hosts=[]):
        if not nginx_conf:
           nginx_conf = DEFAULT_NGINX_CONF

        self._install_package()
        self._setup_logging()
        self._setup_dirs()
        self._setup_config(nginx_conf=nginx_conf)

    def _install_package(self):
        sudo("pkg_add nginx")

    def _setup_logging(self):
        sudo('sed -ie "s/^#nginx\(.*\)/nginx\\1/g" /etc/logadm.conf')
        sudo('logadm')

    def _setup_dirs(self):
        sudo('mkdir -p /var/www/cache-tmp')
        sudo('mkdir -p /var/www/cache')
        sudo('chown -R www:www /var/www')

    def _setup_config(self, nginx_conf=None):
        remote_conv = os.path.join(env.git_working_dir, 'deploy', nginx_conf)
        sudo('ln -sf %s /opt/local/etc/nginx/nginx.conf' % remote_conv)

class UpdateAppServers(Task):
    """
    Build app servers list in your load balancer nginx config.

    Finds your load banlancer nginx config by looking up
    the attribute on the task and rebuilds the list of
    app servers.

    Changes made by this task are not commited to your repo, or deployed
    anywhere automatically. You should review any changes and commit and
    deploy as appropriate.

    This is a serial task, that should not be called directly
    with any remote hosts as it performs no remote actions.
    """

    START_DELM = "## Start App Servers ##"
    END_DELM = "## End App Servers ##"
    LINE = "server   %s:8000 max_fails=5  fail_timeout=60s;"
    START = None
    END = None

    name = 'update_app_servers'
    serial = True

    def _update_file(self, nginx_conf, section):
        file_path = os.path.join(env.deploy_path, nginx_conf)
        text = [self.START_DELM]
        if self.START:
            text.append(self.START)

        for ip in env.config_object.get_list(section, env.config_object.INTERNAL_IPS):
            text.append(self.LINE % ip)

        if self.END:
            text.append(self.END)
        text.append(self.END_DELM)

        txt = "\\n".join(text)
        new_path = file_path + '.bak'
        cmd = "awk '{\
                tmp = match($0, \"%s\"); \
                if (tmp) { \
                    print \"%s\"; \
                    while(getline>0){tmp2 = match($0, \"%s\"); if (tmp2) break;} \
                    next;} \
                {print $0}}' %s > %s" %(self.START_DELM, txt, self.END_DELM,
                                        file_path, new_path)
        local(cmd)
        local('mv %s %s' %(new_path, file_path))

    def run(self, section=None, nginx_conf=None):
        assert section and nginx_conf
        self._update_file(nginx_conf, section)

class UpdateAllowedIPs(UpdateAppServers):
    """
    Build allowed servers list in your app server nginx config.

    Finds your app server nginx config by looking up
    the attribute on the task and rebuilds the list of
    app servers.

    Changes made by this task are not commited to your repo, or deployed
    anywhere automatically. You should review any changes and commit and
    deploy as appropriate.

    This is a serial task, that should not be called directly
    with any remote hosts as it performs no remote actions.
    """

    START_DELM = "## Start Allowed IPs ##"
    END_DELM = "## End Allowed IPs ##"
    LINE = "set_real_ip_from  %s;"
    END = "real_ip_header    X-Cluster-Client-Ip;"

    name = 'update_allowed_ips'

update_app_servers = UpdateAppServers()
update_allowed_ips = UpdateAllowedIPs()
setup = NginxInstall()
