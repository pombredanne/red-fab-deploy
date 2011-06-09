from fab_deploy.aws import create_bucket_if_needed
from fab_deploy.conf import fab_config
from fab_deploy.package import package_install, compile_and_install
from fabric import colors
from fabric.context_managers import settings
from fabric.contrib.files import append, sed
from fabric.operations import sudo
from fabric.state import env
from fabric.utils import warn
from time import sleep

def s3fs_install(id, name, address, stage, options, **kwargs):
    
    ''' Install s3fs '''
    
    with settings(warn_only = True):
        if sudo('s3fs --version'):
            warn(colors.yellow('s3fs is already installed.'))
            return
    
    package_install(['automake', 'build-essential', 'libcurl4-openssl-dev', 'libxml2-dev'])
    compile_and_install('http://downloads.sourceforge.net/project/fuse/fuse-2.X/2.8.5/fuse-2.8.5.tar.gz?use_mirror=autoselect')
    compile_and_install('http://s3fs.googlecode.com/files/s3fs-1.40.tar.gz')
    
def s3fs_setup(id, name, address, stage, options, **kwargs):
        
    create_bucket_if_needed(options['bucket'])
    
    append('/etc/passwd-s3fs', "%s:%s" % (fab_config['aws_access_key_id'], fab_config['aws_secret_access_key']), True)
    sudo('chmod 640 /etc/passwd-s3fs')
    sed('/etc/fstab', '^.*?%s.*$' % options['bucket'], '', use_sudo=True)
    append('/etc/fstab', 's3fs#%s  %s  fuse    allow_other,nobootwait     0       0' % (options['bucket'], options['mountpoint']), True)
    sleep(1)
    with settings(warn_only=True): #HACK
         sudo('mkdir -p %s' % options['mountpoint'])
         sudo('umount %s' % options['mountpoint'])
    sudo('mount %s' % options['mountpoint'])
