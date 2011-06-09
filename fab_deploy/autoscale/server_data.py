from fabric.operations import sudo

def get_data():
    ''' Retrieve stage, server type, and cluster name from server.  Returns dict of those. '''
    return {'stage': sudo('cat /etc/red_fab_deploy_stage'),
            'server_type': sudo('cat /etc/red_fab_deploy_server_type'),
            'cluster': sudo('cat /etc/red_fab_deploy_cluster'),
            'instance_type': sudo('cat /etc/red_fab_deploy_instance_type')}

def set_data(data):
    ''' Save stage, server type, and cluster name to server.  Takes dict of those. '''
    sudo('echo "%s" > /etc/red_fab_deploy_stage' % data['stage'])
    sudo('echo "%s" > /etc/red_fab_deploy_server_type' % data['server_type'])
    sudo('echo "%s" > /etc/red_fab_deploy_cluster' % data['cluster'])
    sudo('echo "%s" > /etc/red_fab_deploy_instance_type' % data['instance_type'])
