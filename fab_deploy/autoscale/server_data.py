from fabric.operations import sudo, run, local, env
from simplejson import loads, dumps

def get_data():
    ''' Retrieve stage, server type, and cluster name from server.  Returns dict of those. '''
    if env.host_string:
        cmd = run
    else:
        cmd = local
    
    try:
        return loads(cmd('cat /etc/red_fab_deploy_data'))
    except:
        return {
            'stage': cmd('cat /etc/red_fab_deploy_stage'),
            'server_type': cmd('cat /etc/red_fab_deploy_server_type'),
            'cluster': cmd('cat /etc/red_fab_deploy_cluster'),
            'instance_type': cmd('cat /etc/red_fab_deploy_instance_type')}

def set_data(data):
    ''' Save stage, server type, and cluster name, and instance_type to server.  Takes dict of those. '''
    sudo('echo "%s" > /etc/red_fab_deploy_data' % dumps(data).replace('"', '\"'))
