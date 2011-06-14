from fabric.operations import sudo
from simplejson import loads, dumps

def get_data():
    ''' Retrieve stage, server type, and cluster name from server.  Returns dict of those. '''
    try:
        return loads(sudo('cat /etc/red_fab_deploy_data'))
    except:
        return {
            'stage': sudo('cat /etc/red_fab_deploy_stage'),
            'server_type': sudo('cat /etc/red_fab_deploy_server_type'),
            'cluster': sudo('cat /etc/red_fab_deploy_cluster'),
            'instance_type': sudo('cat /etc/red_fab_deploy_instance_type')}

def set_data(data):
    ''' Save stage, server type, and cluster name, and instance_type to server.  Takes dict of those. '''
    sudo('echo "%s" > /etc/red_fab_deploy_data' % dumps(data).replace('"', '\"'))
