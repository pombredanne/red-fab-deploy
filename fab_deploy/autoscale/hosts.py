from fab_deploy.autoscale.server_data import get_data
from fab_deploy.aws import ec2_instance, ec2_instances
from fab_deploy.conf import fab_config, fab_data
from fab_deploy.constants import SERVER_TYPE_DB, SERVER_TYPE_WEB
from fabric.api import env

def set_hosts(hosts):
    ''' Set hosts based on instance id or public dns name '''
    env.hosts = []
    for host in hosts:
        if isinstance(host, str) and host.startswith('i-'):
            host = ec2_instance(host)
        if not isinstance(host, basestring):
            host = host.public_dns_name
        env.hosts.append('ubuntu@%s' % host)

def localhost():
    ''' Sets hosts to localhost '''
    set_hosts(['localhost'])

def find_servers(stage, cluster):
    '''Asks EC2 for servers with a given stage and cluster.  Returns list of servers.'''
    config = fab_config.cluster(cluster)
    data = fab_data.cluster(cluster)
    server_type = config.get('server_type')

    return [server for server in ec2_instances() if 
        (stage == str(server.tags.get('Stage')) and (server_type is None or server_type == str(server.tags.get('Server Type'))))\
            or server.image_id == data.get('image')]

def autoscale_template_instances(stage = None, server_type = None):
    ''' Set hosts to master and template instances *only* for given stage/server_type '''
    env.stage = stage or env.stage
    
    hosts = []
    for cluster, settings in fab_config['clusters'].iteritems():
        if server_type and not settings.get('server_type') == server_type:
            continue
    
        if u'master' in fab_data['clusters'][cluster]['instances']:
            hosts.append(fab_data['clusters'][cluster]['instances']['master'])
        hosts.append(fab_data['clusters'][cluster]['instances']['template'])
        
    set_hosts(hosts)

def autoscaling_servers(stage = None, cluster = None):
    ''' Set hosts to *all* servers with same stage/cluster as current machine, or with provided stage/cluster'''
    if stage: # For debugging
        data = {'stage': stage, 'cluster': cluster}
    else:
        data = get_data()

    set_hosts(find_servers(data['stage'], data['cluster']))

def autoscaling_web_servers(stage = None, cluster = None):
    ''' Set hosts to *running* web servers related to current machine
        (either in same cluster if web, or in associated cluster if available), 
        or with provided stage/cluster'''

    if stage and cluster: # For debugging
        data = {'stage': stage, 'cluster': cluster}
    else:
        data = get_data()

    config = fab_config.get(data['cluster'])
    if config.get('server_type') == SERVER_TYPE_WEB:
        pass
    elif config.get('with_web_cluster'):
        data['cluster'] = config['with_web_cluster']
    else:
        raise NotImplementedError('Cound not find web autoscale cluster')

    servers = [server for server in find_servers(data['stage'], data['cluster']) if str(server.status) == 'running']

    # We now have all of the web servers...
    set_hosts(servers)

def original_master(stage = None, cluster = None):
    ''' Set hosts to original master db related to current machine,
    (either in same cluster if db, or in associated cluster if available), 
     or with provided stage/cluster '''

    if stage and cluster: # For debugging
        data = {'stage': stage, 'cluster': cluster}
    else:
        data = get_data()
        
    config = fab_config.get(data['cluster'])
    if config.get('server_type') == SERVER_TYPE_DB:
        pass
    elif config.get('with_db_cluster'):
        data['cluster'] = config['with_db_cluster']
    else:
        raise NotImplementedError('Cound not find db autoscale cluster')

    config = fab_config.get(data['cluster'])
    master_id = data['nodes'].get('master')

    try:
        master = ec2_instance(master_id)
        if str(master.state) == 'running':
            set_hosts([master])
        else:
            set_hosts([])
    except:
        set_hosts([])
