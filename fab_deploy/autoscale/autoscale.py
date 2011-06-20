''' Autoscaling '''
from boto.ec2.autoscale import AutoScaleConnection, LaunchConfiguration
from boto.ec2.elb import ELBConnection, HealthCheck
from boto.exception import BotoServerError, EC2ResponseError
from fab_deploy.autoscale.server_data import get_data, set_data
from fab_deploy.autoscale.util import update_fab_deploy
from fab_deploy.aws import ec2_connection, ec2_instance, save_as_ami, ec2_region, ec2_location, aws_connection_opts
from fab_deploy.conf import fab_config, fab_data, import_string
from fab_deploy.constants import SERVER_TYPE_WEB, SERVER_TYPE_DB
from fab_deploy.db.postgresql import pgpool_set_hosts
from fab_deploy.deploy import install_services, deploy_project, make_active
from fab_deploy.machine import ec2_authorize_port, create_instance, update_instances
from fab_deploy.package import package_install
from fab_deploy.server.web import web_server_restart
from fab_deploy.system import set_hostname, prepare_server
from fab_deploy.utils import setup_hosts, append, find_instances
from fab_deploy.virtualenv import virtualenv
from fabric import colors
from fabric.api import run, sudo, env, put, warn, abort, local as fab_local
from fabric.contrib import console
from fabric.decorators import runs_once
from time import sleep
import os
import re
import webbrowser

def local(cmd, *args, **kwargs):
    return fab_local(re.sub('\s+', ' ', cmd), *args, **kwargs)

def scit(hostname):
    try:
        s, c, it = hostname.split('-')
        return s,c,it
    except ValueError:
        return hostname.split('-', 1) + [None]

@runs_once
def go_start(stage = None, key_name = None):
    ''' Open ports, startup instances. '''
    #TODO: generate key?
    
    env.stage = stage or env.stage
    
    ec2_authorize_port('default', 'tcp', '22')
    ec2_authorize_port('default', 'tcp', '80')
    ec2 = ec2_connection()

    instances = []
    needsips = []
    
    if 'machines' not in fab_data: fab_data['machines'] = {}
    if env.stage not in fab_data['machines']: fab_data['machines'][env.stage] = {}
    
    # Create and start instances
    for cluster, settings in fab_config['clusters'].iteritems():
        data = fab_data.cluster(cluster)
        if settings.get('autoscale'):
            
            machines_to_start = [['template', 'template', False]]
            if settings['server_type'] == SERVER_TYPE_DB: 
                machines_to_start.insert(0, ['master', 'master', True])
        
        elif settings.get('count'):
            machines_to_start = [[str(i), '', False] for i in xrange(settings['count'])]
            
        else:
            machines_to_start = [[cluster, '', False]]
        
        if not console.confirm('Do you wish to stage %i servers for cluster "%s", named: %s' 
                               % (len(machines_to_start),
                                  cluster,
                                  ', '.join('%s-%s%s' % (env.stage, cluster, '-' + m[0] if m[0] != cluster else '') for m in machines_to_start)),
                               default=False):
            abort(colors.red('Aborting instance deployment.'))

        for name, instance_type, needs_static_ip in machines_to_start:
            instance = create_instance('%s-%s%s' % (env.stage, cluster, '-' + name if name != cluster else ''),
                key_name = key_name or fab_config['key_name'],
                location = fab_config['region'],
                image_id = settings.get('initial_image') or settings.get('image') or fab_config['image'],
                size = settings['size'],
                tags = {'Cluster': cluster, 'Stage': env.stage, 'Server Type': settings.get('server_type',''), 'Instance Type': instance_type})
            instances.append(instance)
            if needs_static_ip:
                needsips.append([data, instance])
            if 'instances' not in data: data['instances'] = {}
            data['instances'][name] = instance.id
            fab_data['machines'][env.stage][name] = {'id': instance.id} # Backwards Compat

    # Wait for instances to start
    print colors.green('Waiting for instances to start...')
    while any(instance.update() != 'running' for instance in instances):
        sleep(1)
    print colors.green('All Nodes Started')

    # Set up static IPS
    for data, instance in needsips:
        address = ec2.allocate_address()
        ec2.associate_address(instance.id, address.public_ip)
        data['static-ip'] = address.public_ip
        print colors.green('Static IP Created')
    
    update_instances()
    setup_hosts()

def go_setup_autoscale_masters(stage = None):
    ''' Setup and install software on autoscale master (first) '''
    my_id = run('curl http://169.254.169.254/latest/meta-data/instance-id')
    tags = ec2_instance(my_id).tags
    stage, cluster, instance_type = tags[u'Name'].split('-')
    if instance_type == 'master':
        return go_setup(stage)

def go_setup_autoscale_templates(stage = None):
    ''' Setup and install software on autoscale templates (second!) '''
    my_id = run('curl http://169.254.169.254/latest/meta-data/instance-id')
    tags = ec2_instance(my_id).tags
    stage, cluster, instance_type = tags[u'Name'].split('-')
    if instance_type != 'master':
        return go_setup(stage)

def go_setup(stage = None):
    ''' Install the correct services on each machine '''
    stage = stage or env.stage
    if not stage:
        raise Exception(colors.red('No stage provided'))

    # Set up hostname, instance data by introspecting tags
    my_id = run('curl http://169.254.169.254/latest/meta-data/instance-id')
    instance = ec2_instance(my_id)
    name = instance.tags[u'Name']
    stage, cluster, instance_type = scit(name)
    options = fab_config.cluster(cluster)
    cluster_data = fab_data.cluster(cluster)
    print cluster_data
    data = {'stage': stage,
            'server_type': options.get('server_type'),
            'cluster': cluster,
            'instance_type': instance_type,
            'master_ip': (cluster_data.get('static-ip') or fab_data.cluster(options.get('with_db_cluster')) or {}).get('static-ip')}
    
    set_hostname(name)
    set_data(data)
    
    # Determine if a master/slave relationship exists for databases in config - #TODO not sure how to unify these approaches
    master = None    
    replication = False
    
    if options.get('autoscale'):
        if instance_type == 'master':
            replication = True
        elif instance_type == 'template' and 'postgresql' in options['services']:
            options['services']['postgresql']['slave'] = True
            master = ec2_instance(fab_data.cluster(cluster)['instances']['master']).public_dns_name
            replication = True
            
    elif 'slave' in options:
        # Are we a slave?
        master = find_instances(clusters = options['slave'])[0].public_dns_name
        replication = True

    else:
        # Are we a master?
        for name, values in fab_config['clusters'].iteritems():
            for db in ['mysql','postgresql']:
                if values.get(db,{}).get('slave') == str(env.host_string).split('@')[-1]:
                    replication = True
    
    prepare_server()
    print options
    install_services(my_id, name, instance.public_dns_name, stage, options, replication = replication, master = master)

    if 'pgpool' in options['services']: #TODO: move this
        dbinstances = fab_data.cluster(options['with_db_cluster'])['instances']
        pgpool_set_hosts(options['services']['pgpool']['password'], ec2_instance(dbinstances['master']), [ec2_instance(dbinstances['template'])])

    if options.get('autoscale'):
        package_install('fabric')
        with virtualenv():
            run('pip install -e git+git://github.com/daveisaacson/red-fab-deploy.git#egg=fab_deploy')
        
        #grab_from_web('http://ec2-downloads.s3.amazonaws.com/AutoScaling-2010-08-01.zip')
        #grab_from_web('http://ec2-downloads.s3.amazonaws.com/AutoScaling-2010-08-01.zip')')
        #append('/home/ubuntu/.bashrc', 'export PATH=$PATH:/home/ubuntu/AutoScaling-2010-08-01/bin/:/home/ubuntu/CloudWatch-2010-08-01/bin/')

        try:
            put(os.path.join(env.conf['FILES'], 'rc.local.%s.sh' % options['server_type']),
                '/etc/rc.local', use_sudo = True)
            sudo('chmod 755 /etc/rc.local')
        except ValueError:
            warn(colors.yellow('No rc.local file found for server type %s' % options['server_type']))
            
        append('~/.ssh/config', 'StrictHostKeyChecking no')

    if options.get('post_setup'):
        import_string(options['post_setup'])()

def go_deploy_tag(tagname, stage = None, force = False, use_existing = False, full = True):
    ''' Deploy tag 'tagname' to template servers.
     Autoscaling Non-web servers get it too (although not with a virtualenv) so they have confs and fabric stuff '''

    stage = stage or env.stage
    data = get_data()
    options = fab_config.cluster(data['cluster'])
    
    if options.get('autoscale') or 'uwsgi' in options['services'] or 'apache' in options['services']:
        deploy_project(tagname, force = force, use_existing = use_existing, with_full_virtualenv = data.get('server_type') != SERVER_TYPE_DB)
        
        if full:
            make_active(tagname)
            if fab_config.get('key_location_relative'):
                run('chmod 600 %s' % os.path.join('/srv/active', fab_config['key_location_relative']))
            if options.get('post_activate'):
                import_string(options['post_activate'])()
            if 'uwsgi' in options['services'] or 'apache' in options['services']:
                web_server_restart()

def go_save_templates(stage = None):
    ''' Images templates to s3, registers them '''
    stage = stage or env.stage
    if not stage:
        raise Exception(colors.red('No stage provided'))

    stage, cluster, instance_type = scit(run('hostname'))
    if instance_type == 'template':
        data = fab_data.cluster(cluster)
        data['image'] = save_as_ami(cluster, deregister = data.get('image'))

def go_launch_autoscale(stage = None, force = False, use_existing = False):
    ''' Launches autoscale group with saved templates '''
    stage = stage or env.stage
    if not stage:
        raise Exception(colors.red('No stage provided'))

    data = get_data()
    cluster = data['cluster']
    instance_type = data['instance_type']
    
    if instance_type != 'template': return

    values = fab_config.cluster(cluster)
    data = fab_data.cluster(cluster)

    conn = AutoScaleConnection(fab_config['aws_access_key_id'], fab_config['aws_secret_access_key'],
                           region = ec2_region('%s.autoscaling.amazonaws.com' % ec2_location()))

    print colors.blue('Processing group %s' % cluster)
    as_existing = conn.get_all_groups(names = [cluster])
    if as_existing:
        if force:
            as_existing[0].shutdown_instances()
            print 'Waiting for instances to shut down...'
            while as_existing[0].instances:
                sleep(1)
                as_existing = conn.get_all_groups(names = [cluster])
            sleep(5)
            as_existing[0].delete()
        elif not use_existing:
            raise Exception(colors.red('Autoscaling group exists.  Use force=True to override or use_existing=True to keep going'))

    lc = conn.get_all_launch_configurations(names = ['%s-launch-config' % cluster])
    if lc:
        if force:
            lc[0].delete()
        elif not use_existing:
            raise Exception(colors.red('Launch config exists.  Use force=True to override or use_existing=True to keep going'))


    if 'load_balancer' in values:
        lb_values = values['load_balancer']
        elbconn = ELBConnection(env.conf['AWS_ACCESS_KEY_ID'], env.conf['AWS_SECRET_ACCESS_KEY'],
                                region = ec2_region('elasticloadbalancing.%s.amazonaws.com' % ec2_location()))

        try:
            existing = elbconn.get_all_load_balancers(load_balancer_names = ['%s-load-balancer' % values['load_balancer']['name']])
        except BotoServerError:
            existing = None
        if existing:
            if use_existing:
                balancer = existing
            else:# To avoid deleting load balancers on live servers, LBs won't be deleted by fab-deploy
                raise Exception(colors.red('Load balancer exists.  Use use_existing=True to keep going or manually delete.'))
            #TODO: warn if load balancer instances already exist, this will block autoscaling from using it
            
        if not existing or force:
            balancer = elbconn.create_load_balancer(lb_values['name'], zones = [fab_config['availability_zone']],
                                            listeners = [(v['port'], v['port'], v['protocol']) for v in lb_values['listeners']])
            print colors.green('Load Balancer created.')

            health_check = HealthCheck(target = lb_values['target'], interval = 45, timeout = 30,
                                       healthy_threshold = 2, unhealthy_threshold = 2)
            balancer.configure_health_check(health_check)
            print colors.green('  Health Check attached.')

            if 'cookie-cluster' in lb_values:
                elbconn.create_app_cookie_stickiness_policy(lb_values['cookie-cluster'], balancer.name, '%s-cookie-policy' % cluster)
                print colors.green('  Cookie Stickiness policy attached.')
    else:
        balancer = None

    # Launch Configuration
    if not lc or force:
        lc = LaunchConfiguration(name = '%s-launch-config' % cluster, image_id = data['image'], key_name = fab_config['key_name'])
        conn.create_launch_configuration(lc)
        print colors.green('Launch Configuration %s Created.' % lc.name)

    # Autoscaling Group
    #TODO: make sure this stuff is installed
    if not as_existing or force:
        data = {'cluster': cluster,
                'region': ec2_location(),
                'availability_zone': fab_config['availability_zone'],
                'min_size': values['count_range'][0],
                'max_size': values['count_range'][1],
                'lcname': lc.name,
                'lbcmd': '--load-balancers ' + balancer.name if balancer else '',
                'min_cpu': values['cpu_range'][0],
                'max_cpu': values['cpu_range'][1],
                'cert': fab_config['aws_x509_certificate'],
                'key': fab_config['aws_x509_private_key'],
                }

        local('''as-create-auto-scaling-group %(cluster)s \
                -C %(cert)s -K %(key)s \
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

        data['scale_up_policy'] = local('''as-put-scaling-policy \
                -C %(cert)s -K %(key)s \
                --name %(cluster)s-scale-up-policy \
                --region %(region)s \
                --auto-scaling-group %(cluster)s \
                --type ChangeInCapacity \
                --adjustment=2 \
                --cooldown 120''' % data)

        data['scale_down_policy'] = local('''as-put-scaling-policy \
                -C %(cert)s -K %(key)s \
                --name %(cluster)s-scale-down-policy \
                --region %(region)s \
                --auto-scaling-group %(cluster)s \
                --type ChangeInCapacity \
                --adjustment=-1 \
                --cooldown 120''' % data)

        local('''mon-put-metric-alarm %(cluster)s-high-cpu-alarm \
                -C %(cert)s -K %(key)s \
                --region %(region)s \
                --metric-name CPUUtilization \
                --namespace "AWS/EC2" \
                --dimensions "AutoScalingGroupName=%(cluster)s" \
                --comparison-operator GreaterThanThreshold \
                --period 120 \
                --evaluation-periods 1 \
                --statistic Average \
                --threshold %(max_cpu)s \
                --alarm-actions %(scale_up_policy)s''' % data)

        local('''mon-put-metric-alarm %(cluster)s-high-cpu-alarm \
                -C %(cert)s -K %(key)s \
                --region %(region)s \
                --metric-name CPUUtilization \
                --namespace "AWS/EC2" \
                --dimensions "AutoScalingGroupName=%(cluster)s" \
                --comparison-operator LessThanThreshold \
                --period 120 \
                --evaluation-periods 1 \
                --statistic Average \
                --threshold %(min_cpu)s \
                --alarm-actions %(scale_down_policy)s''' % data)

        if balancer:
            print colors.green('Autoscaling done.  Load balancer is %s' % balancer.dns_name)
            print balancer.__dict__
            #webbrowser.open(balancer.dns_name)

#        ag = AutoScalingGroup(connection = conn,
#                              group_name = cluster,
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
#        run('as-update-auto-scaling-group %s --health-check-type ELB --grace-period 240 --default-cooldown 120 --desired-capacity %s' % (cluster, values['min-size']))
#        print colors.green('Autoscaling Group Created.')
#        
#        if 'min-cpu' in values and 'max-cpu' in values:
#            # Not yet supported by boto-stable
#    #        # Scaling Policies
#    #        policy_cpu_up = ScalingPolicy(connection = conn,
#    #                               cluster = '%s-cpu-up-policy' % cluster,
#    #                               adjustment_type = 'ChangeInCapacity',
#    #                               as_name = cluster,
#    #                               scaling_adjustment = 2,
#    #                               cooldown = 120) #http://boto.cloudhackers.com/ref/ec2.html#boto.ec2.autoscale.policy.ScalingPolicy
#    #        conn.create_scaling_policy(policy_cpu_up)
#    #        
#    #        policy_cpu_down = ScalingPolicy(connection = conn,
#    #                               cluster = '%s-cpu-down-policy' % cluster,
#    #                               adjustment_type = 'ChangeInCapacity',
#    #                               as_name = cluster,
#    #                               scaling_adjustment = -1,
#    #                               cooldown = 120) 
#    #        conn.create_scaling_policy(policy_cpu_down)
#    #        
#    #        # Metric Alarm & Actions
#    #        cwconn = CloudWatchConnection(env.conf['AWS_ACCESS_KEY_ID'], env.conf['AWS_SECRET_ACCESS_KEY'],
#    #                            region=ec2_region('elasticloadbalancing.%s.amazonaws.com' % ec2_location()))
#    #        
#    #        alarm_cpu_up = MetricAlarm(connection = cwconn,
#    #                               cluster = '%s-cpu-up-alarm',
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
#    #        print colors.green('  Policies and Alarms Attached.')
#            
#            tr = Trigger(cluster = '%s-trigger' % cluster,
#                         autoscale_group = ag,
#                         dimensions = [('AutoScalingGroupName', ag.cluster)],
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
#            print colors.green('  Trigger attached.')

@runs_once
def go_stop_autoscale(stage = None, clusters = None):
    ''' Stops autoscaling clusters.  Specify by stage (here or in env.stage), or names of clusters, not both.  Clusters takes precedence'''
    env.stage = stage or env.stage
    if env.stage and not clusters:
        clusters = fab_config['clusters'].keys()
    
    conn = AutoScaleConnection(fab_config['aws_access_key_id'], fab_config['aws_secret_access_key'],
                               region = ec2_region('%s.autoscaling.amazonaws.com' % ec2_location()))

    for cluster in clusters:
        print colors.blue('Stopping group %s' % cluster)
        as_existing = conn.get_all_groups(names = [cluster])
        if not as_existing:
            abort(colors.red('Could not find autoscaling group %s' % cluster))
        as_existing[0].shutdown_instances()
        
    print 'Waiting for instances to shut down...'
    
    for cluster in clusters:
        as_existing = conn.get_all_groups(names = [cluster])
        while as_existing[0].instances:
            sleep(1)
            as_existing = conn.get_all_groups(names = [cluster])
    sleep(5)
    
    for cluster in clusters:
        as_existing = conn.get_all_groups(names = [cluster])
        as_existing[0].delete()
