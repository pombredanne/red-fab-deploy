import subprocess
import urlparse
import os

from fabric.api import env
from fabric.task_utils import crawl

def get_answer(prompt):
    result = None
    while result == None:
        r = raw_input(prompt + ' (y or n)')
        if r == 'y':
            result = True
        elif r == 'n':
            result = False
        else:
            print "Please enter y or n"
    return result

def _command(command, shell=False):
    proc = subprocess.Popen(command, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, shell=shell)
    o, e = proc.communicate()
    if proc.returncode > 0:
        raise Exception(e)
    return o

def call_command(*commands):
    return _command(commands)

def call_shell_command(command):
    return _command(command, shell=True)

def gather_remotes():
    raw_remote = call_command('git', 'remote', '-v')
    remotes = {}
    for line in raw_remote.splitlines():
        parts = line.split()
        remotes[parts[0]] = urlparse.urlparse(parts[1]).netloc
    return remotes

def get_remote_name(host, prefix, name=None):
    assert host and prefix
    if not host in env.git_reverse:
        count = len(env.git_reverse)

        while True:
            if not name or name in env.git_remotes:
                count = count + 1
                name = prefix + str(count)
            else:
                env.git_reverse[host] = name
                env.git_remotes[name] = host
                break
    else:
        name = env.git_reverse[host]

    return name

def get_config_filepath(conf, default):
    if not conf:
       conf = default

    if not conf.startswith('/'):
        conf = os.path.join(env.deploy_path,conf)

    return conf

def get_task_instance(name):
    from fabric import state
    return crawl(name, state.commands)
