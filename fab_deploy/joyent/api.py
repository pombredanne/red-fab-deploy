import sys
import time

from fabric.api import env, execute
from fabric.tasks import Task

from fab_deploy import functions

from smartdc import DataCenter

DEFAULT_PACKAGE = 'Small 1GB'
DEFAULT_DATASET = 'smartos64'

class New(Task):
    name = 'add_server'

    def run(self, **kwargs):
        assert not env.hosts
        if not env.get('joyent_account'):
            print "To use the joyent api you must add a joyent_account value to your env"
            sys.exit()

        setup_name = 'setup.%s' % kwargs.get('type')

        task = functions.get_task_instance(setup_name)

        default_dataset = DEFAULT_DATASET
        default_package = DEFAULT_PACKAGE

        if task:
            if hasattr(task, 'dataset'):
                default_dataset = task.dataset
            if hasattr(task, 'server_size'):
                default_package = task.server_size
        else:
            print "I don't know how to add a %s server" % kwargs.get('type')
            sys.exit()

        location = kwargs.get('data_center')
        if not location and env.get('joyent_default_data_center'):
            location = env.joyent_default_data_center
        elif not location:
            print "You must supply an data_center argument or add a joyent_default_data_center attribute to your env"
            sys.exit()

        key_name = raw_input('Enter your ssh key name: ')
        key_id = '/%s/keys/%s' % ( env.joyent_account, key_name)
        sdc = DataCenter(location=location, key_id=key_id)

        new_args = {
            'name' : kwargs.get('name'),
            'dataset' : kwargs.get('data_set', default_dataset),
            'metadata' : kwargs.get('metadata', {}),
            'tags' : kwargs.get('tags', {}),
            'package' : kwargs.get('package', default_package)
        }

        machine = sdc.create_machine(**new_args)

        public_ip = machine.public_ips[0]
        print "added machine %s" % public_ip
        host_string = 'admin@%s' % public_ip

        sys.stdout.write("waiting for machine to be ready")
        while machine.status() != 'running':
            sys.stdout.write('.')
            time.sleep(5)
        print '  done'

        execute(setup_name, name=kwargs.get('name'), hosts=[host_string])

add_server = New()
