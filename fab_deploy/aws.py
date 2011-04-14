from boto.ec2.autoscale import AutoScaleConnection, AutoScalingGroup, LaunchConfiguration
#from boto.ec2.autoscale.policy import AdjustmentType, Alarm, ScalingPolicy
#from boto.ec2.cloudwatch.alarm import MetricAlarm
from boto.ec2.elb import ELBConnection, HealthCheck
from boto.exception import BotoServerError
from boto.regioninfo import RegionInfo
from fab_deploy.db.postgresql import *
from fab_deploy.deploy import *
from fab_deploy.machine import *
from fab_deploy.package import *
from fab_deploy.system import *
from fab_deploy.utils import *
from time import sleep
import boto
import boto.ec2
import fabric.api
import fabric.colors
import fabric.contrib
import libcloud.security
import os
import sys

def ec2_instances():
    ec2 = ec2_connection()
    return [r.instances[0] for r in ec2.get_all_instances()]

def ec2_location():
    return get_provider_dict()['location'][:-1]

def aws_connection_opts():
    return {'aws_access_key_id': fabric.api.env.conf['AWS_ACCESS_KEY_ID'],
            'aws_secret_access_key': fabric.api.env.conf['AWS_SECRET_ACCESS_KEY'],
            'region': ec2_region(ec2_location())}

    
def ec2_region(endpoint):
    return RegionInfo(name='Region', endpoint=endpoint)

def ec2_connection():
    ec2 = boto.ec2.connect_to_region(ec2_location(),
                        aws_access_key_id = fabric.api.env.conf['AWS_ACCESS_KEY_ID'],
                        aws_secret_access_key = fabric.api.env.conf['AWS_SECRET_ACCESS_KEY'])
    return ec2

def ec2_instance(id):
    ec2 = ec2_connection()
    return ec2.get_all_instances([id])[0].instances[0]

def ec2_instance_with(func):
    ec2 = ec2_connection()
    return [r.instances[0] for r in ec2.get_all_instances if func(r.instances[0])][0]

def get_machine(stage, node_name):
    config = get_provider_dict()
    return config[stage][node_name]

def create_bucket_if_needed(name):
    from boto.s3.connection import S3Connection
    s3 = S3Connection(fabric.api.env.conf['AWS_ACCESS_KEY_ID'],
                      fabric.api.env.conf['AWS_SECRET_ACCESS_KEY'])
    if not any(r for r in s3.get_all_buckets() if str(r.name) == str(name)):
        s3.create_bucket(name, location=ec2_location())

def save_as_ami(name, deregister = None):
    config = get_provider_dict()
    arch = 'i386' if re.search('i\d86', fabric.api.run('uname -m')) else 'x86_64'
    # Copy pk and cert to /tmp, somehow
    fabric.api.put(fabric.api.env.conf['AWS_X509_PRIVATE_KEY'], '/tmp/pk.pem')
    fabric.api.put(fabric.api.env.conf['AWS_X509_CERTIFICATE'], '/tmp/cert.pem')
    
    fabric.contrib.files.sed('/etc/apt/sources.list', 'universe$', 'universe multiverse', use_sudo=True)
    package_update()
    package_install('ec2-ami-tools', 'ec2-api-tools')
    
    if deregister:
        with fabric.api.settings(warn_only=True):
            fabric.api.sudo('ec2-deregister -C /tmp/cert.pem -K /tmp/pk.pem --region %s %s' % (ec2_location(), deregister))
    
    fabric.api.sudo('rm -rf /tmp/%s*' % name)
    fabric.api.sudo('ec2-bundle-vol -c /tmp/cert.pem -k /tmp/pk.pem -u %s -s 10240 -r %s -p %s'\
                     % (fabric.api.env.conf['AWS_ID'], arch, name))
    fabric.api.sudo('ec2-upload-bundle -b %s -m /tmp/%s.manifest.xml -a %s -s %s --location %s'\
                     % (fabric.api.env.conf['AWS_AMI_BUCKET'], name,
                        fabric.api.env.conf['AWS_ACCESS_KEY_ID'], fabric.api.env.conf['AWS_SECRET_ACCESS_KEY'], ec2_location()))
    result = fabric.api.sudo('ec2-register -C /tmp/cert.pem -K /tmp/pk.pem --region %s %s/%s.manifest.xml -n %s'\
                             % (ec2_location(), fabric.api.env.conf['AWS_AMI_BUCKET'], name, name))
    fabric.api.run('rm /tmp/pk.pem')
    fabric.api.run('rm /tmp/cert.pem')
    
    ami = result.split()[1]
    return ami
        
def create_elastic_ip(stage, node_name):
    ec2 = ec2_connection()
    
    address = ec2.allocate_address()
    ec2.associate_address(get_machine(stage, node_name)['id'], address)
    
    return 'ec2-%s.%s.compute.amazonaws.com' % (address.replace('.', '-'), ec2_location())
