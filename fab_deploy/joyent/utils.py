from fabric.api import task, run

@task
def get_ip(interface, hosts=[]):
    return run(get_ip_command(interface))

def get_ip_command(interface):
    if not interface:
        interface = 'net1'
    return 'ifconfig %s | grep inet | grep -v inet6 | cut -d ":" -f 2 | cut -d " " -f 2' % interface
