from boto.ec2.autoscale import AutoScaleConnection
from fab_deploy.autoscale.hosts import find_servers
from fab_deploy.autoscale.server_data import get_data
from fab_deploy.aws import ec2_connection, aws_connection_opts, ec2_instance_with
from fab_deploy.conf import fab_config, fab_data
from fab_deploy.constants import SERVER_TYPE_DB
from fab_deploy.db.postgresql import pgpool_set_hosts
from fabric.operations import local, run, sudo
from fabric.state import env
import re

def update_db_servers(stage = None, cluster = None):
    
    ''' Find *running* db servers associated with current host, or stage/cluster if provided.  Set to pgpool hosts.'''

    if stage and cluster: # For debugging
        data = {'stage': stage, 'cluster': cluster}
    else:
        data = get_data()

    config = fab_config.get(data['cluster'])

    if config['server_type'] == SERVER_TYPE_DB:
        pass
    elif config.get('with_db_cluster'):
        data['cluster'] = config['with_db_cluster']
    else:
        raise NotImplementedError('Cound not find db autoscale cluster')

    servers = [server for server in find_servers(data['stage'], data['cluster']) if str(server.status) == 'running']

    # We now have all of the db servers...
    pgpool_set_hosts(*servers)

def sync_data():
    ''' Sync postgres data from master to self (slave), using pgpool settings to find current master.  Assume at /data '''
    
    config = open('/etc/pgpool.conf').read()
    match = re.search('backend_hostname0\s*=\s*(\w-.)', config)
    master = match.group(1)

    local('''scp -ri %s ubuntu@%s:/data/* /data/''' % (env.key_filename[0], master))
    local('chown -R postgres:postgres /data')


def dbserver_failover(old_node_id, old_host_name, old_master_id):
    ''' On db failover, promotes slave to master if necessary.  Deems old host unhealthy.
    
    Runs on web host (local) when failover occurs.  Accesses new master db host (run/sudo).'''

    ec2 = ec2_connection()
    my_id = run('curl http://169.254.169.254/latest/meta-data/instance-id')
    data = get_data()

    data = fab_data.get(data['cluster'])

    if old_node_id == old_master_id:
        # We broke the master!
        # Touch failover file to make master
        sudo('touch /data/failover')

        # Give master ip address
        ec2.associate_address(my_id, fab_data['static-ip'])
        sudo('service pgpool reload')
        #local('pcp_attach_node 10 127.0.0.1 9898 pgpool %s 0' % settings['services']['postgresql']['password'])

    else:
        # We broke the slave!
        pass

    # Kill the old server
    conn = AutoScaleConnection(**aws_connection_opts())

    instance = ec2_instance_with(lambda i: i.public_dns_name == old_host_name)
    conn.set_instance_health(instance.id, 'Unhealthy', should_respect_grace_period = False)
