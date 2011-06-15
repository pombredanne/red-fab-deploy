from boto.ec2.connection import EC2Connection
from boto.regioninfo import RegionInfo
from boto.s3.connection import S3Connection
from fab_deploy.conf import fab_config
from fab_deploy.machine import get_provider_dict
from fab_deploy.package import package_update, package_install
from fabric.context_managers import settings
from fabric.api import run, put, sudo
import boto.ec2
import fabric.contrib.files
import re

def ec2_instances():
    ''' Returns a list of ec2 instances '''
    ec2 = ec2_connection()
    return [r.instances[0] for r in ec2.get_all_instances()]

def ec2_location():
    ''' Returns the current ec2 region as text'''
    if 'region' in fab_config:
        return fab_config['region']
    else:
        return get_provider_dict()['location'][:-1]

def ec2_region(endpoint):
    ''' Returns a RegionInfo object (for passing to connections) for the provided endpoint (text location)''' 
    return RegionInfo(name='Region', endpoint=endpoint)

def aws_connection_opts():
    ''' Returns a dict of connection opts for boto ec2 connections '''
    return {'aws_access_key_id': fab_config['aws_access_key_id'],
            'aws_secret_access_key': fab_config['aws_secret_access_key'],
            'region': ec2_region(ec2_location())}
    
def ec2_connection():
    ''' Returns an ec2 connection '''
    ec2 = boto.ec2.connect_to_region(ec2_location(),
                        aws_access_key_id = fab_config['aws_access_key_id'],
                        aws_secret_access_key = fab_config['aws_secret_access_key'])
    return ec2

def ec2_instance(id):
    ''' Returns the Instance with the given id'''
    ec2 = ec2_connection()
    return ec2.get_all_instances([id])[0].instances[0]

def ec2_instance_with(func):
    ''' Returns the first instance that func(instance) returns True for '''
    ec2 = ec2_connection()
    instances = [r.instances[0] for r in ec2.get_all_instances() if func(r.instances[0])]
    return instances[0] if instances else None

def create_bucket_if_needed(name):
    opts = aws_connection_opts()
    del opts['region']
    s3 = S3Connection(**opts)
    if not any(r for r in s3.get_all_buckets() if str(r.name) == str(name)):
        s3.create_bucket(name, location=ec2_location())

def save_as_ami(name, deregister = None):
    ''' Saves and registers and returns an ami of name 'name' to the default ami bucket.  Optionally deregisters another AMI'''
    arch = 'i386' if re.search('i\d86', run('uname -m')) else 'x86_64'
    # Copy pk and cert to /tmp, somehow
    put(fab_config['aws_x509_certificate'], '/tmp/cert.pem')
    put(fab_config['aws_x509_private_key'], '/tmp/pk.pem')
    
    fabric.contrib.files.sed('/etc/apt/sources.list', 'universe$', 'universe multiverse', use_sudo=True)
    package_update()
    package_install('ec2-ami-tools', 'ec2-api-tools')
    
    if deregister:
        with settings(warn_only=True):
            sudo('ec2-deregister -C /tmp/cert.pem -K /tmp/pk.pem --region %s %s' % (ec2_location(), deregister))
    
    sudo('rm -rf /tmp/%s*' % name)
    sudo('ec2-bundle-vol -c /tmp/cert.pem -k /tmp/pk.pem -u %s -s 10240 -r %s -p %s'\
                     % (fab_config['aws_id'], arch, name))
    sudo('ec2-upload-bundle -b %s -m /tmp/%s.manifest.xml -a %s -s %s --location %s'\
                     % (fab_config['ami_bucket'], name,
                        fab_config['aws_access_key_id'], fab_config['aws_secret_access_key'], ec2_location()))
    result = sudo('ec2-register -C /tmp/cert.pem -K /tmp/pk.pem --region %s %s/%s.manifest.xml -n %s'\
                             % (ec2_location(), fab_config['ami_bucket'], name, name))
    run('rm /tmp/pk.pem')
    run('rm /tmp/cert.pem')
    
    ami = result.split()[1]
    return ami
