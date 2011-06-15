from fabric.operations import sudo, run, local, env
from simplejson import loads, dumps

def local_run(cmd):
    return local(cmd, capture=True)

def get_data():
    ''' Retrieve stage, server type, and cluster name from server.  Returns dict of those. '''
    if env.host_string:
        cmd = run
    else:
        cmd = local_run
    
    return loads(cmd('cat /etc/red_fab_deploy_data').replace("'", '"'))

def set_data(data):
    ''' Save stage, server type, and cluster name, and instance_type to server.  Takes dict of those. '''
    sudo('echo "%s" > /etc/red_fab_deploy_data' % dumps(data).replace(r'"', r"'"))
    sudo('echo "%s" > /etc/red_fab_deploy_cluster' % data['cluster'])
