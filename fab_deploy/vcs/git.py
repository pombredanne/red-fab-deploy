from fabric.api import local, run
from fab_deploy.conf import fab_config
import re

def export(tagname,do_local=True):
    """ Export the repo with tagname to cwd """
    
    command = 'git clone --depth 1 %s %s' % (fab_config['repo'], tagname)
    if tagname != 'head':
        command += ' && git checkout %s' % tagname
    command += '&& rm -rf %s/.git*' % tagname
    
    if do_local:
        local(command)
    else:
        run(command)
