from boto.ec2.autoscale import AutoScaleConnection
from fab_deploy.virtualenv import virtualenv
from fabric.api import env
from fabric.decorators import runs_once, hosts
from functools import wraps
from pprint import pformat
import fabric.api
import fabric.colors
import fabric.contrib.files
import os
import re
import simplejson
from compiler.ast import Return


def _codename(distname, version, id):
    patterns = [
        ('lenny',    ('debian', '^5', '')),
        ('squeeze',  ('debian', '^6', '')),
        ('lucid',    ('Ubuntu', '^10.04', '')),
        ('maverick', ('Ubuntu', '^10.10', '')),
    ]
    for name, p in patterns:
        if re.match(p[0], distname) and re.match(p[1], version) and re.match(p[2], id):
            return name

def detect_os():
    if 'conf' in fabric.api.env and 'OS' in fabric.api.env.conf:
        return fabric.api.env.conf['OS']
    output = fabric.api.run('python -c "import platform; print platform.linux_distribution()"')
    name = _codename(*eval(output))
    fabric.api.puts('%s detected' % name)
    return name

def run_as(user):
    """
    Decorator.  Runs fabric command as specified user.  It is most useful to run
    commands that require root access to server:

        from fabric.api import run
        from fab_deploy.utils import run_as

        @run_as('root')
        def package_update():
            fabric.api.run('package update')
    
    """
    def decorator(func):
        @wraps(func)
        def inner(*args, **kwargs):
            old_user, host, port = fabric.network.normalize(fabric.api.env.host_string)
            fabric.api.env.host_string = fabric.network.join_host_strings(user, host, port)
            result = func(*args, **kwargs)
            fabric.api.env.host_string = fabric.network.join_host_strings(old_user, host, port)
            return result
        return inner
    return decorator

def update_env():
    """
    Updates :attr:`env.conf` configuration with some defaults and converts
    it to _AttributeDict (that's a dictionary subclass enabling attribute
    lookup/assignment of keys/values).

    Call :func:`update_env` at the end of each server-configuring function:

        from fab_deploy import update_env

        def my_site():
            fabric.api.env.hosts = ['my_site@example.com']
            fabric.api.env.conf = dict(
                INSTANCE_NAME = 'projectname',
                PROVIDER = 'ec2_us_east',
                REPO = 'http://some.repo.com/projectname/',
            )
            update_env()
    """
    
    fabric.api.env.conf = getattr(fabric.api.env, 'conf', {})
    
    defaults = fabric.state._AttributeDict(
        DB            = 'mysql',       # Choose from 'mysql' or 'postgresql'
        DB_PASSWD     = 'password',    # DB root user password, please replace
        INSTANCE_NAME = 'projectname', # This should be the project name
        PROVIDER      = 'ec2_us_east', # use 'ec2_us_east' or 'ec2_us_west'
        RSYNC_EXCLUDE = '',            # files to exclude
        SERVER_TYPE   = 'nginx',       # Choose from 'apache' or 'nginx'
        VCS           = 'svn',         # Currently only svn works
        VCS_TAGS      = 'tags',        # Could be 'tags' or 'branches' in svn

        # these options shouldn't be set by user
        ENV_DIR  = '/srv/active/env/',
        SRC_DIR  = os.path.join('/srv', fabric.api.env.conf['INSTANCE_NAME']),
        FILES    = os.path.join(os.path.dirname(__file__),'templates'),
    )
    defaults.update(fabric.api.env.conf)
    fabric.api.env.conf = defaults

    # expand VCS name to full import path
    for vcs in ['svn','tar']: 
        if fabric.api.env.conf.VCS == vcs:
            fabric.api.env.conf.VCS = 'fab_deploy.vcs.%s' % vcs
            break

def set_hosts(stage='development',username='ubuntu',machine=''):
    """
    The stage specifies which group of machines to set the hosts for

    The username specifies which user to use when setting the hosts

    The machine is optional and can specify a specific machine within
    a stage to set the host for.
    """
    host_types = {
        'db'     : [],
        'load'   : [],
        'server' : [],
        'other'  : [],
    }
    PROVIDER = simplejson.loads(open('fabric.conf','r').read()) 
    if stage in PROVIDER['machines']:
        for name in PROVIDER['machines'][stage]:
            if (machine and machine == name) or not machine:
                instance_dict = PROVIDER['machines'][stage][name]
                if 'public_ip' in instance_dict:
                    public_ip = instance_dict['public_ip']
                    services  = instance_dict['services']
                    for ip in public_ip:
                        host = '%s@%s' % (username,ip)
                        # Set up databases first
                        if list(set(['mysql','postgresql','postgresql-client']) & set(services)):
                            for db in ['mysql','postgresql','postgresql-client']:
                                # Slaves can be appended to the end, but full 
                                # db instances should be given priority
                                if db in services and 'slave' in services[db]:
                                    host_types['db'].append(host)
                                elif db in services:
                                    host_types['db'].insert(0,host)
                        # Set up load balancer or servers
                        elif list(set(['nginx','apache']) & set(services)):
                            host_types['load'].append(host)
                        # Set up these last
                        elif list(set(['uwsgi']) & set(services)):
                            host_types['server'].append(host)
                        # Catch all other hosts
                        else:
                            host_types['other'].append(host)
                else:
                    fabric.api.warn(fabric.colors.yellow('No public IPs found for %s in %s' % (name,stage)))
    
    # The order in which these are combined is important
    hosts = host_types['db'] + host_types['load'] + host_types['server'] + host_types['other']
    fabric.api.env.hosts = hosts
    update_env()
    
def delete_pyc():
    """ Deletes *.pyc files from project source dir """
    fabric.api.run("find . -name '*.pyc' -delete")

def debug_env():
    """ Prints env values. Useful for debugging. """
    fabric.api.puts(pformat(fabric.api.env))

def append(filename, text, use_sudo=False, partial=True, escape=True):
    """
    Append string (or list of strings) ``text`` to ``filename``. Modified from fabric.contrib to actually work.

    When a list is given, each string inside is handled independently (but in
    the order given.)

    If ``text`` is already found in ``filename``, the append is not run, and
    None is returned immediately. Otherwise, the given text is appended to the
    end of the given ``filename`` via e.g. ``echo '$text' >> $filename``.

    The test for whether ``text`` already exists defaults to a full line match,
    e.g. ``^<text>$``, as this seems to be the most sensible approach for the
    "append lines to a file" use case. You may override this and force partial
    searching (e.g. ``^<text>``) by specifying ``partial=True``.

    Because ``text`` is single-quoted, single quotes will be transparently 
    backslash-escaped. This can be disabled with ``escape=False``.

    If ``use_sudo`` is True, will use `sudo` instead of `run`.

    .. versionchanged:: 0.9.1
        Added the ``partial`` keyword argument.

    .. versionchanged:: 1.0
        Swapped the order of the ``filename`` and ``text`` arguments to be
        consistent with other functions in this module.
    .. versionchanged:: 1.0
        Changed default value of ``partial`` kwarg to be ``False``.
    """
    func = use_sudo and fabric.api.sudo or fabric.api.run
    # Normalize non-list input to be a list
    if isinstance(text, str):
        text = [text]
    for line in text:
        regex = '^' + re.escape(line) + ('' if partial else '$')
        if (fabric.contrib.files.exists(filename) and line
            and fabric.contrib.files.contains(filename, regex, use_sudo=use_sudo)):
            print filename, regex, fabric.contrib.files.contains(filename, regex, use_sudo=use_sudo)
            continue
        line = line.replace('"', r'\"') if escape else line
        func('echo "%s" >> %s' % (line, filename))

def sudo_put(file, loc):
    tmploc = '/home/ubuntu/%s' % os.path.split(file)[1]
    fabric.api.put(file, tmploc)
    fabric.api.sudo('mv %s %s' % (tmploc, loc))
    fabric.api.sudo('chown root:root %s' % loc)
    
def combine(*dikts):
    master = {}
    for dikt in dikts:
        master.update(dikt)
    return master


def list_hosts():
    ''' Lists hosts! Useful for debugging. '''
    print env.hosts

def stage(st):
    env.stage = st

def cluster(name):
    env.clusters = [name]
    
def server_type(type):
    env.server_types = [type]

def instance_type(type):
    env.instance_types = [type]

def setup_hosts(clusters = None, server_types = None, instance_types = None):
    #HAAAAAAAAAAAAACK
    class FakeString(str):
        def __init__(self, *args, **kwargs):
            super(FakeString, self).__init__(*args, **kwargs)
            self.command_run = True
    if getattr(env.command, 'command_run', None):
        return
    env.command = FakeString(env.command)
    ####
    
    set_hosts(find_instances(clusters, server_types, instance_types))
    
def find_instances(clusters = None, server_types = None, instance_types = None):
    
    print fabric.colors.green('Finding hosts...')
    clusters = env.clusters = clusters or getattr(env, 'clusters', None)
    server_types = env.server_types = server_types or getattr(env, 'server_types', None)
    instance_types = env.server_types = clusters or getattr(env, 'instance_types', None)
    
    from fab_deploy.aws import aws_connection_opts, ec2_connection
    from fab_deploy.conf import fab_config
    from fab_deploy.autoscale.hosts import set_hosts
    from fab_deploy.aws import ec2_region, ec2_location, ec2_instance
    ec2 = ec2_connection()
    
    if isinstance(clusters, basestring):
        clusters = [clusters]
    if isinstance(server_types, basestring):
        server_types = [server_types]
    if isinstance(instance_types, basestring):
        instance_types = [instance_types]
    
    instances = {}
    if not hasattr(env, 'instances'):
        # Get autoscaled instances
        conn = AutoScaleConnection(fab_config['aws_access_key_id'], fab_config['aws_secret_access_key'],
                               region = ec2_region('%s.autoscaling.amazonaws.com' % ec2_location()))
        
        ec2_clusters = dict((group.name, group) for group in conn.get_all_groups(clusters))
        for cluster, config in fab_config['clusters'].iteritems():
            group = ec2_clusters[cluster]
            for instance_object in group.instances:
                instance = ec2_instance(instance_object.instance_id)
                if instance.state != 'running':
                    continue
                instances[instance] = {'stage': env.stage,
                                       'cluster': cluster,
                                       'server_type': config.get('server_type'),
                                       'instance_type': 'autoscale'}
        
        # Get manually created instances
        for request in ec2.get_all_instances():
            for instance in request.instances:
                if instance in instances or str(instance.tags.get('Stage')) != env.stage or instance.state != 'running':
                    continue
                instances[instance] = {'stage': str(instance.tags.get('Stage')),
                                       'cluster': str(instance.tags.get('Cluster')),
                                       'server_type': str(instance.tags.get('Server Type')),
                                       'instance_type': str(instance.tags.get('Instance Type'))}
        
        env.instances = instances
    
    # Filter 
    instances = dict((instance, attrs) for instance, attrs in env.instances.iteritems()
         if (not server_types or attrs['server_type'] in server_types)\
         and (not instance_types or attrs['instance_type'] in instance_types)\
         and (not clusters or attrs['cluster'] in clusters))
         
    # return in order masters... templates ... autoscale... other
#    these_instance_types = ['master', 'template', 'autoscale']
#    instances = sorted(instances.iteritems(),
#                       key=lambda (k, value): these_instance_types.index(value['instance_type']) if value['instance_type'] in these_instance_types else 999)

    return instances.keys()