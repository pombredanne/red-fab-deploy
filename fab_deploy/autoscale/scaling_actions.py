from boto.ec2.autoscale import AutoScaleConnection
from fab_deploy.autoscale.server_data import get_data
from fab_deploy.aws import ec2_connection, aws_connection_opts, ec2_instance_with, ec2_region, ec2_location
from fab_deploy.conf import fab_config, fab_data
from fab_deploy.constants import SERVER_TYPE_DB
from fab_deploy.db.postgresql import pgpool_set_hosts
from fab_deploy.utils import find_instances
from fabric.operations import local, run, sudo
from fabric.state import env
import re
#from fab_deploy.autoscale.hosts import find_servers



def _db_servers_for_cluster(cluster = None, master_ip = None):
    

    cluster = cluster or get_data()['cluster']
    master_ip = master_ip or get_data()['master_ip']

    config = fab_config.cluster(cluster)

    if config['server_type'] == SERVER_TYPE_DB:
        pass
    elif config.get('with_db_cluster'):
        cluster = config['with_db_cluster']
    else:
        raise NotImplementedError('Cound not find db autoscale cluster')

    instances = find_instances(clusters=[cluster])
    master = [i for i in instances if i.ip_address == master_ip][0]
    slaves = [i for i in instances if i.ip_address != master_ip]
    
    return master, slaves

def update_db_servers(cluster = None, master_ip = None):
    ''' Find *running* db servers associated with current host, or cluster if provided.  Set to pgpool hosts.'''
    pgpool_set_hosts(*_db_servers_for_cluster(cluster, master_ip))
    sudo('service pgpool restart') #TODO: reload isn't working for some reason

def sync_data(cluster = None):
    ''' Sync postgres data from master to self (slave)'''
    
    master, slaves = _db_servers_for_cluster(cluster)
    
    local('''scp -ri %s ubuntu@%s:/data/* /data/''' % (env.key_filename[0], master.public_dns_name))
    local('chown -R postgres:postgres /data')


def dbserver_failover(old_node_id, old_host_name, old_master_id):
    ''' On db failover, promotes slave to master if necessary.  Deems old host unhealthy.
    
    Run by web host (local) when failover occurs.  Runs on new master db host (run/sudo).'''

    ec2 = ec2_connection()
    my_id = run('curl http://169.254.169.254/latest/meta-data/instance-id')
    data = get_data()

    if old_node_id == old_master_id:
        # We broke the master!
        # Touch failover file to make master
        sudo('touch /data/failover')

        # Give master ip address
        ec2.associate_address(my_id, data['master_ip'])
        sudo('service pgpool reload')
        #local('pcp_attach_node 10 127.0.0.1 9898 pgpool %s 0' % settings['services']['postgresql']['password'])

    else:
        # We broke the slave!
        pass

    # Kill the old server
    conn = AutoScaleConnection(fab_config['aws_access_key_id'], fab_config['aws_secret_access_key'],
                               region = ec2_region('%s.autoscaling.amazonaws.com' % ec2_location()))

    instance = ec2_instance_with(lambda i: i.public_dns_name == old_host_name)
    conn.set_instance_health(instance.id, 'Unhealthy', should_respect_grace_period = False)
