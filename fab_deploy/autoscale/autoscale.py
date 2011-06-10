''' Autoscaling '''
from boto.ec2.autoscale import AutoScaleConnection, LaunchConfiguration
from boto.ec2.elb import ELBConnection, HealthCheck
from boto.exception import BotoServerError, EC2ResponseError
from fab_deploy.autoscale.hosts import autoscale_template_instances
from fab_deploy.autoscale.server_data import get_data, set_data
from fab_deploy.autoscale.util import update_fab_deploy
from fab_deploy.aws import ec2_connection, ec2_instance, save_as_ami, ec2_region, ec2_location
from fab_deploy.conf import fab_config, fab_data, import_string
from fab_deploy.constants import SERVER_TYPE_WEB, SERVER_TYPE_DB
from fab_deploy.db.postgresql import pgpool_set_hosts
from fab_deploy.deploy import install_services, deploy_project, make_active
from fab_deploy.machine import ec2_authorize_port, create_instance
from fab_deploy.package import package_install
from fab_deploy.server.web import web_server_restart
from fab_deploy.system import set_hostname, prepare_server
from fabric import colors
from fabric.api import local, run, sudo, env, put, warn
from fabric.decorators import runs_once
from time import sleep
import os

@runs_once
def go_prepare_autoscale(stage = None):
    ''' Open ports, startup db master, db and web templates. '''
    
    env.stage = stage or env.stage
    
    ec2_authorize_port('default', 'tcp', '22')
    ec2_authorize_port('default', 'tcp', '80')
    ec2 = ec2_connection()

    instances = []
    needsips = []
    
    # Create and start instances
    for cluster, settings in fab_config['clusters'].iteritems():
        if not settings.get('autoscale'):
            continue

        data = fab_data.cluster(cluster)
        if settings['server_type'] == SERVER_TYPE_DB: 
            # Do the master first
            instance = create_instance('%s-%s-master' % (env.stage, cluster),
                                    stage = stage,
                                    key_name = fab_config['key_name'],
                                    location = fab_config['region'],
                                    image_id = settings['initial_image'],
                                    size = settings['size'],
                                    server_type = settings['server_type'])
            instances.append(instance)
            needsips.append([data, instance])
            if 'instances' not in data: data['instances'] = {}
            data['instances']['master'] = instance.id

        instance = create_instance('%s-%s-template' % (env.stage, cluster),
                               stage = stage,
                               key_name = fab_config['key_name'],
                               location = fab_config['region'],
                               image_id = settings['initial_image'],
                               size = settings['size'],
                               server_type = settings['server_type'])

        instances.append(instance)
        if 'instances' not in data: data['instances'] = {}
        data['instances']['template'] = instance.id

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
        
    # Save and set hosts
    # print colors.green('Settings Saved')
    # autoscale_template_instances()

def go_setup_autoscale_masters(stage = None):
    ''' Setup and install software on autoscale master (first) '''
    my_id = run('curl http://169.254.169.254/latest/meta-data/instance-id')
    tags = ec2_instance(my_id).tags
    stage, cluster, instance_type = tags[u'Name'].split('-')
    if instance_type == 'master':
        _go_setup_autoscale(stage)

def go_setup_autoscale_templates(stage = None):
    ''' Setup and install software on autoscale templates (second!) '''
    my_id = run('curl http://169.254.169.254/latest/meta-data/instance-id')
    tags = ec2_instance(my_id).tags
    stage, cluster, instance_type = tags[u'Name'].split('-')
    if instance_type != 'master':
        _go_setup_autoscale(stage)

def _go_setup_autoscale(stage = None):
    ''' Base function for setup on masters and templates '''
    stage = stage or env.stage
    if not stage:
        raise Exception(colors.red('No stage provided'))

    # Now we're on the instance
    my_id = run('curl http://169.254.169.254/latest/meta-data/instance-id')
    address = run('curl http://169.254.169.254/latest/meta-data/public-hostname')

    tags = ec2_instance(my_id).tags
    stage, cluster, instance_type = tags[u'Name'].split('-')
    data = {'stage': stage, 'server_type': fab_config.cluster(cluster)['server_type'], 'cluster': cluster, 'instance_type': instance_type}
    options = fab_config.cluster(cluster)

    set_hostname(tags[u'Name'])
    set_data(data)

    master = None
    if instance_type == 'template' and 'postgresql' in options['services']:
        options['services']['postgresql']['slave'] = True
        master = ec2_instance(fab_data.cluster(cluster)['instances']['master']).public_dns_name

    prepare_server()
    install_services(my_id, tags[u'Name'], address, stage, options, replication = True, master = master)

    if 'pgpool' in options['services']:
        dbinstances = fab_data.cluster(options['with_db_cluster'])['instances']
        pgpool_set_hosts([ec2_instance(dbinstances['master']).public_dns_name, ec2_instance(dbinstances['template']).public_dns_name])

    package_install('fabric')
#    grab_from_web('http://ec2-downloads.s3.amazonaws.com/AutoScaling-2010-08-01.zip')
#    grab_from_web('http://ec2-downloads.s3.amazonaws.com/CloudWatch-2010-08-01.zip')
#    append('/home/ubuntu/.bashrc', 'export PATH=$PATH:/home/ubuntu/AutoScaling-2010-08-01/bin/:/home/ubuntu/CloudWatch-2010-08-01/bin/')

    try:
        put(os.path.join(env.conf['FILES'], 'rc.local.%s.sh' % data['server_type']),
                       '/etc/rc.local', use_sudo = True)
        sudo('chmod 755 /etc/rc.local')
    except ValueError:
        warn(colors.yellow('No rc.local file found for server type %s' % data['server_type']))

    import_string(options.get('post_setup'))()

def go_deploy_autoscale(tagname, stage = None, force = False, use_existing = False):
    ''' Deploy tag 'tagname' to template servers.
      Non-web servers get it too (although not with a virtualenv) so they have confs and fabric stuff '''
    
    stage = stage or env.stage
    if not stage:
        raise Exception(colors.red('No stage provided'))

    data = get_data()

    deploy_project(tagname, force = force, use_existing = use_existing, with_full_virtualenv = data['server_type'] != SERVER_TYPE_DB)
    update_fab_deploy()

    make_active(tagname)

    import_string(fab_config.cluster(data['cluster']).get('post_activate'))()

    if data['server_type'] == SERVER_TYPE_WEB:
        web_server_restart()

def go_save_templates(stage = None):
    ''' Images templates to s3, registers them '''
    stage = stage or env.stage
    if not stage:
        raise Exception(colors.red('No stage provided'))

    stage, cluster, instance_type = run('hostname').split('-')
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


    if 'load-balancer' in values:
        lb_values = values['load-balancer']
        elbconn = ELBConnection(env.conf['AWS_ACCESS_KEY_ID'], env.conf['AWS_SECRET_ACCESS_KEY'],
                                region = ec2_region('elasticloadbalancing.%s.amazonaws.com' % ec2_location()))

        try:
            existing = elbconn.get_all_load_balancers(load_balancer_names = ['%s-load-balancer' % values['load-balancer']['cluster']])
        except BotoServerError:
            existing = None
        if existing:
            #if force:
            #    existing[0].delete()
            #elif not use_existing:
                raise Exception(colors.red('Load balancer exists.  Use use_existing=True to keep going or manually delete.'))

        if not existing or force:
            balancer = elbconn.create_load_balancer(lb_values['cluster'], zones = [fab_config['location']],
                                            listeners = [(v['port'], v['port'], v['protocol']) for v in lb_values['listeners']])
            print colors.green('Load Balancer created.')

            health_check = HealthCheck(target = lb_values['target'], interval = 45, timeout = 30,
                                       healthy_threshold = 2, unhealthy_threshold = 2)
            balancer.configure_health_check(health_check)
            print colors.green('  Health Check attached.')

            if 'cookie-cluster' in lb_values:
                elbconn.create_app_cookie_stickiness_policy(lb_values['cookie-cluster'], balancer.name, '%s-cookie-policy' % cluster)
                print colors.green('  Cookie Stickiness policy attached.')

            # For some reason, doing this breaks the connection to the ASG.
#            if values['instances'].get('template'):
#                ec2 = ec2_connection()
#                print ec2_instance(values['instances']['template'])
#                elbconn.register_instances(balancer.cluster, [values['instances']['template']])
#                print colors.green('  Existing template instance added.')
    else:
        balancer = None

    # Launch Configuration
    if not lc or force:
        lc = LaunchConfiguration(name = '%s-launch-config' % cluster, image_id = data['image'], key_name = fab_config['key_name'])
        conn.create_launch_configuration(lc)
        print colors.green('Launch Configuration %s Created.' % lc.name)

    # Autoscaling Group

    if not as_existing or force:
        data = {'cluster': cluster,
                'region': ec2_location(),
                'availability_zone': fab_config['availability_zone'],
                'min_size': values['size_range'][0],
                'max_size': values['size_range'][1],
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
