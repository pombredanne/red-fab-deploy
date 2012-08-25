from fabric.api import run, sudo, env
from fabric.tasks import Task

class GunicornInstall(Task):
    """
    Install gunicorn and set it up with svcadm.
    """

    name = 'setup'

    def run(self):

        sudo('mkdir -p /var/log/gunicorn')
        sudo('chown -R www:www /var/log/gunicorn')

        # Add django log
        sudo('logadm -C 3 -p1d -c -w /var/log/gunicorn/django.log -z 1')
        run('svccfg import /srv/active/deploy/gunicorn/gunicorn.xml')

setup = GunicornInstall()
