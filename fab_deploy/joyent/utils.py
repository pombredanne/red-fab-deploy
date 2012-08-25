import random
from fabric.api import task, run

@task
def get_ip(interface, hosts=[]):
    return run(get_ip_command(interface))

def get_ip_command(interface):
    if not interface:
        interface = 'net1'
    return 'ifconfig %s | grep inet | grep -v inet6 | cut -d ":" -f 2 | cut -d " " -f 2' % interface

def random_password(bit=12):
    """
    generate a password randomly which include
    numbers, letters and sepcial characters
    """
    numbers = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
    small_letters = [chr(i) for i in range(97, 123)]
    cap_letters = [chr(i) for i in range(65, 91)]
    special = ['@', '#', '$', '%', '^', '&', '*', '-']

    passwd = []
    for i in range(bit/4):
        passwd.append(random.choice(numbers))
        passwd.append(random.choice(small_letters))
        passwd.append(random.choice(cap_letters))
        passwd.append(random.choice(special))
    for i in range(bit%4):
        passwd.append(random.choice(numbers))
        passwd.append(random.choice(small_letters))
        passwd.append(random.choice(cap_letters))
        passwd.append(random.choice(special))

    passwd = passwd[:bit]
    random.shuffle(passwd)

    return ''.join(passwd)
