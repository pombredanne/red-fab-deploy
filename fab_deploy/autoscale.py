''' Autoscaling for EC2 (only) '''
from boto.ec2.autoscale import AutoScaleConnection, AutoScalingGroup, LaunchConfiguration
#from boto.ec2.autoscale.policy import AdjustmentType, Alarm, ScalingPolicy
#from boto.ec2.cloudwatch.alarm import MetricAlarm
from boto.ec2.elb import ELBConnection, HealthCheck
from boto.exception import BotoServerError
from boto.regioninfo import RegionInfo
from fab_deploy.db.postgresql import *
from fab_deploy.deploy import *
from fab_deploy.machine import *
from fab_deploy.package import *
from fab_deploy.system import *
from fab_deploy.utils import *
from libcloud.compute.base import NodeImage, NodeLocation, NodeSize
from libcloud.compute.providers import get_driver
from libcloud.compute.types import Provider
from pprint import pprint
from subprocess import Popen
from time import sleep
import boto
import boto.ec2
import fabric.api
import fabric.colors
import fabric.contrib
import libcloud.security
import os
import re
import sys

# EC2 Utility Methods
def ec2_location():
    return get_provider_dict()['location'][:-1]

def ec2_userdata():
    return {'stage': fabric.api.sudo('cat /etc/red_fab_deploy_stage'),
            'server_type': fabric.api.sudo('cat /etc/red_fab_deploy_server_type')}

def ec2_set_data(data):
    fabric.api.sudo('echo "%s" > /etc/red_fab_deploy_stage' % data['stage'])
    fabric.api.sudo('echo "%s" > /etc/red_fab_deploy_server_type' % data['server_type'])
    
def ec2_region(endpoint):
    return RegionInfo(name='Region', endpoint=endpoint)

def ec2_connection():
    ec2 = boto.ec2.connect_to_region(ec2_location(),
                        aws_access_key_id = fabric.api.env.conf['AWS_ACCESS_KEY_ID'],
                        aws_secret_access_key = fabric.api.env.conf['AWS_SECRET_ACCESS_KEY'])
    return ec2

def ec2_instance(id):
    ec2 = ec2_connection()
    return ec2.get_all_instances([id])[0].instances[0]

def ec2_instance_with(func):
    ec2 = ec2_connection()
    return [r.instances[0] for r in ec2.get_all_instances if func(r.instances[0])][0]

def get_machine(stage, node_name):
    config = get_provider_dict()
    return config[stage][node_name]

def create_bucket_if_needed(name):
    from boto.s3.connection import S3Connection
    s3 = S3Connection(fabric.api.env.conf['AWS_ACCESS_KEY_ID'],
                      fabric.api.env.conf['AWS_SECRET_ACCESS_KEY'])
    if not any(r for r in s3.get_all_buckets() if str(r.name) == str(name)):
        s3.create_bucket(name, location=ec2_location())

def save_as_ami(name, deregister = None):
    config = get_provider_dict()
    arch = 'i386' if re.search('i\d86', fabric.api.run('uname -m')) else 'x86_64'
    # Copy pk and cert to /tmp, somehow
    fabric.api.put(fabric.api.env.conf['AWS_X509_PRIVATE_KEY'], '/tmp/pk.pem')
    fabric.api.put(fabric.api.env.conf['AWS_X509_CERTIFICATE'], '/tmp/cert.pem')
    
    fabric.contrib.files.sed('/etc/apt/sources.list', 'universe$', 'universe multiverse', use_sudo=True)
    package_update()
    package_install('ec2-ami-tools', 'ec2-api-tools')
    
    if deregister:
        with fabric.api.settings(warn_only=True):
            fabric.api.sudo('ec2-deregister -C /tmp/cert.pem -K /tmp/pk.pem --region %s %s' % (ec2_location(), deregister))
    
    fabric.api.sudo('rm -rf /tmp/%s*' % name)
    fabric.api.sudo('ec2-bundle-vol -c /tmp/cert.pem -k /tmp/pk.pem -u %s -s 10240 -r %s -p %s'\
                     % (fabric.api.env.conf['AWS_ID'], arch, name))
    fabric.api.sudo('ec2-upload-bundle -b %s -m /tmp/%s.manifest.xml -a %s -s %s --location %s'\
                     % (fabric.api.env.conf['AWS_AMI_BUCKET'], name,
                        fabric.api.env.conf['AWS_ACCESS_KEY_ID'], fabric.api.env.conf['AWS_SECRET_ACCESS_KEY'], ec2_location()))
    result = fabric.api.sudo('ec2-register -C /tmp/cert.pem -K /tmp/pk.pem --region %s %s/%s.manifest.xml -n %s'\
                             % (ec2_location(), fabric.api.env.conf['AWS_AMI_BUCKET'], name, name))
    fabric.api.run('rm /tmp/pk.pem')
    fabric.api.run('rm /tmp/cert.pem')
    
    ami = result.split()[1]
    return ami
        
def create_elastic_ip(stage, node_name):
    ec2 = ec2_connection()
    
    address = ec2.allocate_address()
    ec2.associate_address(get_machine(stage, node_name)['id'], address)
    
    return 'ec2-%s.%s.compute.amazonaws.com' % (address.replace('.', '-'), ec2_location())

def put_file(from_path, to_path):
    fabric.api.put(from_path, to_path)

# Finding other servers

def autoscaling_servers(stage=None):
    ''' To be run on db_server startup.  Finds all webservers. '''
    
    if stage is None:
        stage = ec2_userdata()['stage']
        
    config = get_provider_dict()
    ec2 = ec2_connection()
    fabric.api.env.hosts = []
    for name, options in config['autoscale'][stage].iteritems():

        webservers = [server.instances[0] for server in ec2.get_all_instances() 
                      if (server.instances[0].tags.get('Stage') == unicode(stage))
                          or (server.instances[0].image_id == options.get('image'))]
        fabric.api.env.hosts.extend('ubuntu@%s' % ws.public_dns_name for ws in webservers)
    
    
def autoscaling_webservers(stage=None, autoscale_name=None):
    ''' To be run on db_server startup.  Finds all webservers. '''
    
    if stage is None:
        stage = ec2_userdata()['stage']
    if autoscale_name is None:
        autoscale_name, node_type = run('hostname').rsplit('-', 1)
        
    config = get_provider_dict()
    options = config['autoscale'][stage][autoscale_name]

    ec2 = ec2_connection()
    webservers = [server.instances[0] for server in ec2.get_all_instances() 
                  if (server.instances[0].tags.get('Server Type') == u'web' and server.instances[0].tags.get('Stage') == unicode(stage))
                      or (server.instances[0].image_id == options.get('image'))]
    fabric.api.env.hosts = ['ubuntu@%s' % ws.public_dns_name for ws in webservers]
    
def register_db_server(host):
    
    ''' Register self with (web)servers '''
        
    i = 0
    while True:
        if not fabric.contrib.files.contains('/etc/pgpool.conf', 'backend_hostname%d' % i):
            break
        i += 1
    
    append('/etc/pg_pool.conf', [
        'backend_hostname%d = %s' % (i, host),
        'backend_port%d = 5432' % i,
        'backend_weight%d = 1' % i
    ])
    
    sudo('service pgpool2 reload')
    
    
def oldest_other_webserver(stage=None, autoscale_name=None):
    
    ''' To be run on web server startup.  Finds oldest other webserver (including dev template) '''

    if stage is None:
        stage = ec2_userdata()['stage']
    if autoscale_name is None:
        autoscale_name, node_type = run('hostname').rsplit('-', 1)
    config = get_provider_dict()
    options = config['autoscale'][stage][autoscale_name]

    try:
        fabric.api.local('curl --connect-timeout 5 http://169.254.169.254/latest/meta-data/public-hostname/instance-id')
    except:
        my_id = None
    ec2 = ec2_connection()
    
    webservers = [server.instances[0] for server in ec2.get_all_instances() 
                  if server.instances[0].id != my_id and 
                        ((server.instances[0].tags.get('Server Type') == u'web' and server.instances[0].tags.get('Stage') == unicode(stage))
                         or (server.instances[0].image_id == options.get('image')))]

    webservers.sort(key = lambda w: w.launch_time)

   # while webservers:
    oldest = webservers.pop(0)
        #if fabric.api.local('curl --connect-timeout 5 %s >> /dev/null' % oldest.public_dns_name):
        #    break
    fabric.api.env.hosts = ['ubuntu@%s' % oldest.public_dns_name]
    
def steal_config_file(filename):
    localfile = open(filename, 'w')
    content = sudo('cat %s' % filename)
    localfile.write(content)
    localfile.close()
    
def sync_data():
    ''' Sync postgres data from master to self (slave) '''
    config = open('/etc/pgpool.conf').read()
    match = re.search('backend_hostname0\s*=\s*(\w-.)', config)
    master = match.group(1)
    
    fabric.api.local('''scp -ri %s ubuntu@%s:/data/* /data/''' % (fabric.api.env.key_filename[0], master))
    fabric.api.local('chown -R postgres:postgres /data')
    
def original_db_master():
    ''' Run on webserver to find original master (to stop if needed) '''
    ec2 = ec2_connection()
    my_id = run('curl http://169.254.169.254/latest/meta-data/public-hostname/instance-id')
    autoscale_name, node_type = run('hostname').rsplit('-', 1)
    data = ec2_userdata()
    config = get_provider_dict()
    
    if data['server_type'] != 'db':
        return
    
    original_master = config[data['stage'][autoscale_name]['nodes']['master']]
    
    pgconfig = open('/etc/pgpool.conf').read()
    match = re.search('backend_hostname0\s*=\s*(\w-.)', pgconfig)
    current_master = match.group(1)

    if original_master == current_master:
        set_host(original_master)

def set_host(host):
    fabric.api.env.hosts = ['ubuntu@%s' % host]
    
def dbserver_failover(old_node_id, old_host_name, old_master_id):
    ''' Runs on web host (local) when failover occurs.  Accesses new master db host (run/sudo)'''
    
    ec2 = ec2_connection()
    my_id = run('curl http://169.254.169.254/latest/meta-data/public-hostname/instance-id')
    autoscale_name, node_type = run('hostname').rsplit('-', 1)
    data = ec2_userdata()

    config = get_provider_dict()
    settings = config['autoscale'][data['stage']]

    
    if old_node_id == old_master_id:
        # We broke the master!
        # Touch failover file to make master
        sudo('touch /data/failover')
        
        # Give master ip address
        ec2.associate_address(my_id, settings['static-ip'])
        fabric.api.local('pcp_attach_node 10 127.0.0.1 9898 pgpool %s 0' % settings['services']['postgresql']['password'])
        
    else:
        # We broke the slave!
        pass
    
    # Kill the old server
    conn = AutoScaleConnection(fabric.api.env.conf['AWS_ACCESS_KEY_ID'], fabric.api.env.conf['AWS_SECRET_ACCESS_KEY'],
                               region = ec2_region('%s.autoscaling.amazonaws.com' % ec2_location()))
    
    instance = ec2_instance_with(lambda i: i.public_dns_name == old_host_name)
    conn.set_instance_health(instance.id, 'Unhealthy', should_respect_grace_period = False)

def reload_pgpool_master():
    # Reload node 0, the master
    fabric.api.sudo('pcp_attach_node 10 127.0.0.1 9898 pgpool %s 0' % settings['services']['postgresql']['password'])

def go_prepare_autoscale(stage='development'):
    ec2_authorize_port('default','tcp','22')
    ec2_authorize_port('default','tcp','80')

    fabric.api.env.conf['stage'] = stage
    ec2 = ec2_connection()
    
    config = get_provider_dict()
    nodes = []
    needsips = []
    for name, values in config.get('autoscale', {}).get(stage, {}).iteritems():
        if values['server-type'] == 'db': # Do the master first
            node = create_node('%s-master' % name, keyname = config['key'],
                                       image = get_node_image(values['initial_image']),
                                       size = get_node_size(values['size']), location = config['location'], stage = stage,
                                       server_type = values['server-type'])
            nodes.append(node)
            needsips.append([name, values, node])
            values['nodes'] = dict(values.get('nodes', {}), master = node.id)

        node = create_node('%s-template' % name, keyname = config['key'],
                           image = get_node_image(values['initial_image']),
                           size = get_node_size(values['size']), location = config['location'], stage = stage,
                           server_type = values['server-type'])

        nodes.append(node)
        values['nodes'] = dict(values.get('nodes', {}), template = node.id)
            
        
    print fabric.colors.green('Waiting for nodes to start...')
    instances = [r.instances[0] for r in ec2.get_all_instances([n.name for n in nodes])]
    
    while any(instance.update() != 'running' for instance in instances):
        sleep(1)
    print fabric.colors.green('All Nodes Started')
    
    for name, values, node in needsips:
        address = ec2.allocate_address()
        ec2.associate_address(node.id, address.public_ip)
        values['static-ip'] = address.public_ip
        print fabric.colors.green('Static IP Created')
    write_conf(config)
    print fabric.colors.green('Settings Saved')
    autoscale_template_nodes(stage)
  
def autoscale_template_nodes(stage = 'development', server_type=None):
    fabric.api.env.conf['stage'] = stage
    ec2 = ec2_connection()
    config = get_provider_dict()
    fabric.api.env.hosts = []
    for name, values in config.get('autoscale', {}).get(stage, {}).iteritems():
        if server_type and not values.get('server-type') == server_type:
            continue
        nodes = values.get('nodes', {})
        if u'master' in nodes:
            fabric.api.env.hosts.append('ubuntu@%s' % ec2_instance(nodes[u'master']).public_dns_name)
        fabric.api.env.hosts.append('ubuntu@%s' % ec2_instance(nodes[u'template']).public_dns_name)
    update_env()

def go_setup_autoscale_masters(stage = None):
    my_id = fabric.api.run('curl http://169.254.169.254/latest/meta-data/instance-id')
    tags = ec2_instance(my_id).tags
    autoscale_name, node_type = tags[u'Name'].rsplit('-', 1)
    if node_type == 'master':
        _go_setup_autoscale(stage)
        
def go_setup_autoscale(stage = None):
    my_id = fabric.api.run('curl http://169.254.169.254/latest/meta-data/instance-id')
    tags = ec2_instance(my_id).tags
    autoscale_name, node_type = tags[u'Name'].rsplit('-', 1)
    if node_type != 'master':
        _go_setup_autoscale(stage)
    
def _go_setup_autoscale(stage = None):
    stage = stage or fabric.api.env.conf['stage']
    if not stage:
        fabric.api.error(fabric.colors.red('No stage provided'))

    # Now we're on the node
    config = get_provider_dict()

    my_id = fabric.api.run('curl http://169.254.169.254/latest/meta-data/instance-id')
    address = fabric.api.run('curl http://169.254.169.254/latest/meta-data/public-hostname')
    
    tags = ec2_instance(my_id).tags
    autoscale_name, node_type = tags[u'Name'].rsplit('-', 1)
    options = config['autoscale'][stage][autoscale_name]
    data = {'stage': stage, 'server_type': options['server-type']}

    set_hostname(tags[u'Name'])
    ec2_set_data(data)
    
    master = None
    if node_type == 'template' and 'postgresql' in options['services']:
        options['services']['postgresql']['slave'] = True
        print tags[u'Name']
        master = ec2_instance(options['nodes']['master']).public_dns_name
    
    prepare_server()
    install_services(my_id, tags[u'Name'], address, stage, options, replication=True, master=master)

    if 'pgpool' in options['services']:
        dbnodes = config['autoscale'][stage][options['services']['pgpool']['db_cluster']]['nodes']
        pgpool_set_hosts(ec2_instance(dbnodes['master']).public_dns_name, ec2_instance(dbnodes['template']).public_dns_name)
    
    package_install('fabric')
#    grab_from_web('http://ec2-downloads.s3.amazonaws.com/AutoScaling-2010-08-01.zip')
#    grab_from_web('http://ec2-downloads.s3.amazonaws.com/CloudWatch-2010-08-01.zip')
#    append('/home/ubuntu/.bashrc', 'export PATH=$PATH:/home/ubuntu/AutoScaling-2010-08-01/bin/:/home/ubuntu/CloudWatch-2010-08-01/bin/')
    
    try:
        fabric.api.put(os.path.join(fabric.api.env.conf['FILES'], 'rc.local.%s.sh' % data['server_type']),
                       '/etc/rc.local', use_sudo=True)
    except ValueError:
        fabric.api.warn(fabric.colors.yellow('No rc.local file found for server type %s' % data['server_type']))
    
    fabric.api.env.conf.extra_setup.get(data['server_type'], lambda: None)()
    
def go_deploy_autoscale(tagname, stage = None, force=False, use_existing=False):
    stage = stage or fabric.api.env.conf['stage']
    if not stage:
        fabric.api.error(fabric.colors.red('No stage provided'))

    data = ec2_userdata()

    deploy_project(tagname, force=force, use_existing=use_existing, with_virtualenv = data['server_type'] != 'db')

    make_active(tagname)
 
    fabric.api.env.conf.post_activate.get(data['server_type'], lambda: None)()
    
    if data['server_type'] == 'web':
        web_server_restart()
    
def go_save_templates(stage = None):
    stage = stage or fabric.api.env.conf['stage']
    if not stage:
        fabric.api.error(fabric.colors.red('No stage provided'))

    autoscale_name, node_type = fabric.api.run('hostname').rsplit('-', 1)
    if node_type == 'template':
        config = get_provider_dict()
        ami = save_as_ami(autoscale_name, deregister = config['autoscale'][stage][autoscale_name].get('image'))
        config['autoscale'][stage][autoscale_name]['image'] = ami
        write_conf(config)

def go_launch_autoscale(stage = None, force=False, ignore=False):
    stage = stage or fabric.api.env.conf['stage']
    if not stage:
        fabric.api.error(fabric.colors.red('No stage provided'))

    name, node_type = fabric.api.run('hostname').rsplit('-', 1)
    if node_type != 'template': return
    
    config = get_provider_dict()
    
    conn = AutoScaleConnection(fabric.api.env.conf['AWS_ACCESS_KEY_ID'], fabric.api.env.conf['AWS_SECRET_ACCESS_KEY'],
                               region = ec2_region('%s.autoscaling.amazonaws.com' % ec2_location()))
    
    values = config['autoscale'][stage][name]
    
    print fabric.colors.blue('Processing group %s' % name)
    as_existing = conn.get_all_groups(names=[name])
    if as_existing:
        if force:
            as_existing[0].shutdown_instances()
            print 'Waiting for instances to shut down...'
            while as_existing[0].instances:
                sleep(1)
                as_existing = conn.get_all_groups(names=[name])
            sleep(5)
            as_existing[0].delete()
        elif not ignore:
            fabric.api.error(fabric.colors.red('Autoscaling group exists.  Use force=True to override or ignore=True to keep going'))

    lc = conn.get_all_launch_configurations(names=['%s-launch-config' % name])
    if lc:
        if force:
            lc[0].delete()
        elif not ignore:
            raise Exception(fabric.colors.red('Launch config exists.  Use force=True to override or ignore=True to keep going'))
    
    
    if 'load-balancer' in values:
        lb_values = values['load-balancer']
        elbconn = ELBConnection(fabric.api.env.conf['AWS_ACCESS_KEY_ID'], fabric.api.env.conf['AWS_SECRET_ACCESS_KEY'],
                                region=ec2_region('elasticloadbalancing.%s.amazonaws.com' % ec2_location()))

        try:
            existing = elbconn.get_all_load_balancers(load_balancer_names = ['%s-load-balancer' % values['load-balancer']['name']])
        except BotoServerError:
            existing = None
        if existing:
            if force:
                existing[0].delete()
            elif not ignore:
                fabric.api.error(fabric.colors.red('Load balancer exists.  Use force=True to override or ignore=True to keep going'))
    
        if not existing or force:
            balancer = elbconn.create_load_balancer(lb_values['name'], zones = [config['location']], 
                                            listeners = [(v['port'], v['port'], v['protocol']) for v in lb_values['listeners']])
            print fabric.colors.green('Load Balancer created.')
            
            health_check = HealthCheck(target = lb_values['target'], interval = 45, timeout = 30,
                                       healthy_threshold = 2, unhealthy_threshold = 2)
            balancer.configure_health_check(health_check)
            print fabric.colors.green('  Health Check attached.')
        
            if 'cookie-name' in lb_values:
                elbconn.create_app_cookie_stickiness_policy(lb_values['cookie-name'], balancer.name, '%s-cookie-policy' % name)
                print fabric.colors.green('  Cookie Stickiness policy attached.')
            
            # For some reason, doing this breaks the connection to the ASG.
#            if values['nodes'].get('template'):
#                ec2 = ec2_connection()
#                print ec2_instance(values['nodes']['template'])
#                elbconn.register_instances(balancer.name, [values['nodes']['template']])
#                print fabric.colors.green('  Existing template instance added.')
    else:
        balancer = None
        
    # Launch Configuration
    if not lc or force:
        lc = LaunchConfiguration(name = '%s-launch-config' % name, image_id = values['image'],  key_name = config['key'])
        conn.create_launch_configuration(lc)
        print fabric.colors.green('Launch Configuration Created.')
    
    # Autoscaling Group

    if not as_existing or force:
        data = {'name': name,
                'region': ec2_location(),
                'availability_zone': config['location'],
                'min_size': values['min-size'],
                'max_size': values['max-size'],
                'lcname': lc.name,
                'lbcmd': '--load-balancers ' + balancer.name if balancer else '',
                'min_cpu': values['min-cpu'],
                'max_cpu': values['max-cpu']}
        
        fabric.api.local('''as-create-auto-scaling-group %(name)s \
                --region %(region)s \
                --availability-zones %(availability_zone)s \
                --default-cooldown 120 \
                --desired-capacity %(min_size)s \
                --health-check-type ELB \
                --grace-period 120 \
                --launch-configuration %(lcname)s \
                %(lbcmd)s \
                --min-size %(min_size)s \
                --max-size %(max_size)s''' % data)

        data['scale_up_policy'] = fabric.api.local('''as-put-scaling-policy \
                --name %(name)s-scale-up-policy \
                --region %(region)s \
                --auto-scaling-group %(name)s \
                --type ChangeInCapacity \
                --adjustment=2 \
                --cooldown 120''' % data)
        
        data['scale_down_policy'] = fabric.api.local('''as-put-scaling-policy \
                --name %(name)s-scale-down-policy \
                --region %(region)s \
                --auto-scaling-group %(name)s \
                --type ChangeInCapacity \
                --adjustment=-1 \
                --cooldown 120''' % data)
        
        fabric.api.local('''mon-put-metric-alarm %(name)s-high-cpu-alarm \
                --region %(region)s \
                --metric-name CPUUtilization \
                --namespace "AWS/EC2" \
                --dimensions "AutoScalingGroupName=%(name)s" \
                --comparison-operator GreaterThanThreshold \
                --period 120 \
                --evaluation-periods 1 \
                --statistic Average \
                --threshold %(max_cpu)s \
                --alarm-actions %(scale_up_policy)s''' % data)
        
        fabric.api.local('''mon-put-metric-alarm %(name)s-high-cpu-alarm \
                --region %(region)s \
                --metric-name CPUUtilization \
                --namespace "AWS/EC2" \
                --dimensions "AutoScalingGroupName=%(name)s" \
                --comparison-operator LessThanThreshold \
                --period 120 \
                --evaluation-periods 1 \
                --statistic Average \
                --threshold %(min_cpu)s \
                --alarm-actions %(scale_down_policy)s''' % data)
        
        
        
        
#        ag = AutoScalingGroup(connection = conn,
#                              group_name = name,
#                              availability_zones = [config['location']],
#                              #default_cooldown = 120,
#                              #desired_capacity = values['min-size'],
#                              #health_check_period = 240,
#                              #health_check_type = 'ELB',
#                              launch_config = lc,
#                              load_balancers = [balancer] if balancer else [],
#                              max_size = values['max-size'],
#                              min_size = values['min-size'])
#        conn.create_auto_scaling_group(ag)
#        fabric.api.run('as-update-auto-scaling-group %s --health-check-type ELB --grace-period 240 --default-cooldown 120 --desired-capacity %s' % (name, values['min-size']))
#        print fabric.colors.green('Autoscaling Group Created.')
#        
#        if 'min-cpu' in values and 'max-cpu' in values:
#            # Not yet supported by boto-stable
#    #        # Scaling Policies
#    #        policy_cpu_up = ScalingPolicy(connection = conn,
#    #                               name = '%s-cpu-up-policy' % name,
#    #                               adjustment_type = 'ChangeInCapacity',
#    #                               as_name = name,
#    #                               scaling_adjustment = 2,
#    #                               cooldown = 120) #http://boto.cloudhackers.com/ref/ec2.html#boto.ec2.autoscale.policy.ScalingPolicy
#    #        conn.create_scaling_policy(policy_cpu_up)
#    #        
#    #        policy_cpu_down = ScalingPolicy(connection = conn,
#    #                               name = '%s-cpu-down-policy' % name,
#    #                               adjustment_type = 'ChangeInCapacity',
#    #                               as_name = name,
#    #                               scaling_adjustment = -1,
#    #                               cooldown = 120) 
#    #        conn.create_scaling_policy(policy_cpu_down)
#    #        
#    #        # Metric Alarm & Actions
#    #        cwconn = CloudWatchConnection(fabric.api.env.conf['AWS_ACCESS_KEY_ID'], fabric.api.env.conf['AWS_SECRET_ACCESS_KEY'],
#    #                            region=ec2_region('elasticloadbalancing.%s.amazonaws.com' % ec2_location()))
#    #        
#    #        alarm_cpu_up = MetricAlarm(connection = cwconn,
#    #                               name = '%s-cpu-up-alarm',
#    #                               metric = 'CPUUtilization',
#    #                               namespace = 'AWS/EC2',
#    #                               statistic = 'Average',
#    #                               period = 600,
#    #                               evaluation_periods = 1,
#    #                               threshold = values['min-cpu'],
#    #                               comparison = '>')
#    #        alarm_cpu_up.actions_enabled
#    #        alarm_cpu_up.alarm_actions = [policy_cpu_up.arn]
#    #        cwconn.put_metric_alarm(alarm_cpu_up)
#    #        print fabric.colors.green('  Policies and Alarms Attached.')
#            
#            tr = Trigger(name = '%s-trigger' % name,
#                         autoscale_group = ag,
#                         dimensions = [('AutoScalingGroupName', ag.name)],
#                         measure_name = 'CPUUtilization',
#                         statistic = 'Average',
#                         period = 60,
#                         unit = 'Percent',
#                         lower_threshold = values['min-cpu'],
#                         lower_breach_scale_increment = '-1',
#                         upper_threshold = values['max-cpu'],
#                         upper_breach_scale_increment = '2',
#                         breach_duration = 120)
#            conn.create_trigger(tr)
#            print fabric.colors.green('  Trigger attached.')

def update_fab_deploy(fabfile=None):
    with fabric.api.cd('/srv/active/'):
        with virtualenv():
            fabric.api.sudo('pip install -e -e git://github.com/ff0000/red-fab-deploy.git@autoscaling#egg=fab_deploy')
    if fabfile:
        fabric.api.put(fabfile, '/srv/active/fabfile.py')
        
def list_hosts():
    print fabric.api.env.hosts