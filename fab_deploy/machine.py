"""
Ubuntu image sizes:
    http://alestic.com/
    http://uec-images.ubuntu.com/lucid/current/
"""

from pprint import pprint
import os
import time

import fabric.api
import fabric.colors
import fabric.contrib

import boto
from boto import ec2
import simplejson

from fab_deploy.package import package_install, package_update

#=== CONF Defaults
SERVER = {'nginx':{},'uwsgi':{}}
DB     = {
	'mysql': {
		'name'     :'',     # not default
		'user'     :'',     # not root
		'password' :'',     # not root
		#'slave'    :'db1',  # reference to master database
	},
}

#=== Cloud Defaults
EC2_IMAGE = 'ami-a6f504cf' # Ubuntu 10.10, 32-bit instance
EC2_MACHINES = {
	'development' : {
		'dev1' : {
			'image'      : EC2_IMAGE,
			'placement'  : 'us-east-1b',
			'services'   : dict(SERVER, **DB),
			'size'       : 'm1.small',},
	},
	'production' : {
		# Use the Amazon Elastic Load Balancer
		'web1' : {
			'image'      : EC2_IMAGE,
			'placement'  : 'us-east-1a',
			'services': SERVER,
			'size':'m1.small',},
		'web2' : {
			'image'      : EC2_IMAGE,
			'placement'  : 'us-east-1b',
			'services': SERVER,
			'size':'m1.small',},
		'dbs1' : {
			'image'      : EC2_IMAGE,
			'placement'  : 'us-east-1c',
			'services': DB,
			'size':'m1.small',},
		'dbs2' : {
			'image'      : EC2_IMAGE,
			'placement'  : 'us-east-1d',
			'services': {'slave':'dbs1'},
			'size':'m1.small',},
	},
}

PROVIDER_DICT = {
	'ec2_us_west': {
		'machines'   : EC2_MACHINES,
		'region_id'  : 'us-west-1',
	},
	'ec2_us_east': {
		'machines'   : EC2_MACHINES,
		'region_id'  : 'us-east-1',
	},
}

#=== EC2 Instance Types
EC2_INSTANCE_TYPES = {
    't1.micro': {
        'id': 't1.micro',
        'name': 'Micro Instance',
        'ram': 613,
        'disk': 15,
        'bandwidth': None
    },
    'm1.small': {
        'id': 'm1.small',
        'name': 'Small Instance',
        'ram': 1740,
        'disk': 160,
        'bandwidth': None
    },
    'm1.large': {
        'id': 'm1.large',
        'name': 'Large Instance',
        'ram': 7680,
        'disk': 850,
        'bandwidth': None
    },
    'm1.xlarge': {
        'id': 'm1.xlarge',
        'name': 'Extra Large Instance',
        'ram': 15360,
        'disk': 1690,
        'bandwidth': None
    },
    'c1.medium': {
        'id': 'c1.medium',
        'name': 'High-CPU Medium Instance',
        'ram': 1740,
        'disk': 350,
        'bandwidth': None
    },
    'c1.xlarge': {
        'id': 'c1.xlarge',
        'name': 'High-CPU Extra Large Instance',
        'ram': 7680,
        'disk': 1690,
        'bandwidth': None
    },
    'm2.xlarge': {
        'id': 'm2.xlarge',
        'name': 'High-Memory Extra Large Instance',
        'ram': 17510,
        'disk': 420,
        'bandwidth': None
    },
    'm2.2xlarge': {
        'id': 'm2.2xlarge',
        'name': 'High-Memory Double Extra Large Instance',
        'ram': 35021,
        'disk': 850,
        'bandwidth': None
    },
    'm2.4xlarge': {
        'id': 'm2.4xlarge',
        'name': 'High-Memory Quadruple Extra Large Instance',
        'ram': 70042,
        'disk': 1690,
        'bandwidth': None
    },
    'cg1.4xlarge': {
        'id': 'cg1.4xlarge',
        'name': 'Cluster GPU Quadruple Extra Large Instance',
        'ram': 22528,
        'disk': 1690,
        'bandwidth': None
    },
    'cc1.4xlarge': {
        'id': 'cc1.4xlarge',
        'name': 'Cluster Compute Quadruple Extra Large Instance',
        'ram': 23552,
        'disk': 1690,
        'bandwidth': None
    },
}

def write_conf(instance,filename=''):
	""" Overwrite the conf file with dictionary values """
	if not filename:
		filename = fabric.api.env.conf['CONF_FILE']
	obj = simplejson.dumps(instance, sort_keys=True, indent=4)
	f = open(filename,'w')
	f.write(obj)
	f.close()

def generate_config(provider='ec2_us_east'):
	""" Generate a default json config file for your provider """
	conf_file = fabric.api.env.conf['CONF_FILE']
	if os.path.exists(conf_file):
		if not fabric.contrib.console.confirm("Do you wish to overwrite the config file %s?" % (conf_file), default=False):
			conf_file = os.path.join(os.getcwd(),fabric.api.prompt('Enter a new filename:'))

	write_conf(PROVIDER_DICT[provider],filename=conf_file)
	print fabric.colors.green('Successfully generated config file %s' % conf_file)

def get_provider_dict():
	""" Get the dictionary of provider settings """
	conf_file = fabric.api.env.conf['CONF_FILE']
	return simplejson.loads(open(conf_file,'r').read())

def stage_exists(stage):
	""" Abort if provider does not exist """
	PROVIDER = get_provider_dict()
	if stage not in PROVIDER['machines'].keys():
		fabric.api.abort(fabric.colors.red('Stage "%s" is not available' % stage))

#=== Private Methods

def _get_access_secret_keys():
	""" Get the access and secret keys for the given provider """
	if 'AWS_ACCESS_KEY_ID' in fabric.api.env.conf and \
	   'AWS_SECRET_ACCESS_KEY' in fabric.api.env.conf:
		access_key = fabric.api.env.conf['AWS_ACCESS_KEY_ID']
		secret_key = fabric.api.env.conf['AWS_SECRET_ACCESS_KEY']
	else:
		fabric.api.abort(fabric.colors.red('Must have AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in env'))
	return access_key, secret_key

def _set_access_secret_keys():
	access_key, secret_key = _get_access_secret_keys()
	os.environ['AWS_ACCESS_KEY_ID']     = access_key
	os.environ['AWS_SECRET_ACCESS_KEY'] = secret_key

def _get_region():
	""" Get the region """
	PROVIDER = get_provider_dict()
	region_id = PROVIDER['region_id']
	all_regions = ec2.regions()
	return [r for r in all_regions if r.name == region_id][0]

def _get_stage_machines(stage):
	""" Return a list of server names for stage """
	stage_exists(stage)
	PROVIDER = get_provider_dict()
	return [name for name in PROVIDER['machines'][stage].keys()]

#=== Connection, Keys and Ports

def get_connection():
	""" Get the connection for the given provider """
	_set_access_secret_keys()
	region = _get_region()
	return region.connect()

def ec2_create_key(key_name):
	""" Create a pem key on an amazon ec2 server. """
	resp = get_connection().create_key_pair(key_name)
	key_material = resp.__dict__.get('material')
	if not key_material:
		fabric.api.abort(fabric.colors.red("Key Material was not returned"))
	private_key = '%s.pem' % key_name
	f = open(private_key, 'w')
	f.write(key_material + '\n')
	f.close()
	os.chmod(private_key, 0600)

def ec2_authorize_port(name,protocol,port):

	if protocol not in ['tcp','udp','icmp']:
		fabric.api.abort(fabric.colors.red('Protocol must be one of tcp, udp, or icmp'))
	
	if int(port) < -1 or int(port) > 65535:
		fabric.api.abort(fabric.colors.red('Ports must fall between 0 and 65535'))
		
	params = {
			'group_name': name,
			'ip_protocol': protocol,
			'from_port': port,
			'to_port': port,
			'cidr_ip': '0.0.0.0/0'
			}
	return get_connection().authorize_security_group(**params)
	
#=== List Node Instances

def list_instances():
	""" Return a list of instances """
	reservations = get_connection().get_all_instances()
	instances = []
	for reservation in reservations:
		instances.extend(reservation.instances)
	return instances

def list_images():
	""" Return a list of images """
	return get_connection().get_all_images()

def list_sizes():
	""" Return a list of sizes """
	sizes = []
	for key in EC2_INSTANCE_TYPES.keys():
		sizes.append(EC2_INSTANCE_TYPES[key])
	return sizes

def list_regions():
	""" Return a list of regions """
	_set_access_secret_keys()
	return ec2.regions()

#=== Get Node Instance

def get_instance(name):
	""" Get an instance by name """
	for i in list_instances():
		if 'name' in i.tags.keys() and name == i.tags['name'] and i.state == 'running': 
			return i
	return None

def get_image(image_id):
	""" 
	Return an image from list of available images.
	"""
	return get_connection().get_image(image_id)

def get_size(size_id):
	""" 
	Return a size from list of available sizes.
	"""
	for size in list_sizes():
		if size['id'] == size_id: return size
	return None

def get_region(region_id):
	"""
	Return a region from a list of regions
	"""
	return [r for r in list_regions() if r.name == region_id][0]

#=== Print Singular Node Instances

def print_instance(name):
	""" Pretty print an instance by name """
	instance = get_instance(name)
	if instance:
		pprint(instance.__dict__)

def print_image(image_id):
	""" Pretty print an image by id """
	pprint(get_image(image_id).__dict__)

def print_size(size_id):
	""" Pretty print a size by id """
	pprint(get_size(size_id))

def print_region(region_id):
	""" Pretty print a region by id """
	pprint(get_region(region_id).__dict__)

#=== Print List of Node Instances

def print_instances():
	""" Pretty print the list of instances """
	for i in list_instances(): pprint(i.__dict__)

def print_images():
	""" Pretty print the list of images """
	for i in list_images(): pprint(i.__dict__)

def print_sizes():
	""" Pretty print the list of sizes """
	for s in list_sizes(): pprint(s)

def print_regions():
	""" Pretty print the list of regions """
	for r in list_regions(): pprint(r)

#=== Create and Deploy Nodes

def create_instance(name,**kwargs):
	""" Create an EC2 instance """
	PROVIDER      = get_provider_dict()
	key_name      = kwargs.get('key_name',None)
	image_id      = kwargs.get('image_id',None)
	instance_type = kwargs.get('instance_type','m1.small')
	placement     = kwargs.get('placement','us-east-1b')

	image = get_image(image_id)
	if image:
		reservation = image.run(1,1, 
						key_name      = key_name, 
						instance_type = instance_type, 
						#placement     = placement,
						)
		instance    = reservation.instances[0]

		instance.add_tag('name',name)

		print fabric.colors.green('Instance %s named %s is pending' % (instance,name))
		return instance
	else:
		fabric.api.abort(fabric.colors.red("No image was found that matched id %s" % image_id))

def deploy_instances(stage='development',key_name=None):
	""" Deploy instances based on stage type """
	stage_exists(stage)
	if not key_name:
		fabric.api.abort(fabric.colors.red("Must supply valid key_name."))

	if not fabric.contrib.console.confirm("Do you wish to stage %s servers with the following names: %s?" % (stage, ', '.join(_get_stage_machines(stage))), default=False):
		fabric.api.abort(fabric.colors.red("Aborting instance deployment."))

	# Create new instances
	PROVIDER = get_provider_dict()
	for name in PROVIDER['machines'][stage]:
		inst = PROVIDER['machines'][stage][name]
		if 'id' not in inst or not inst['id']:
			instance = create_instance(name,
				key_name      = key_name,
				image_id      = inst.get('image',None),
				instance_type = inst.get('size','m1.small'),
				placement     = inst.get('placement','us-east-1b'),
				)
			inst.update({'id': instance.id})

			PROVIDER['machines'][stage][name] = inst
		else:
			fabric.api.warn(fabric.colors.yellow("%s machine %s already exists" % (stage,name)))
	
	write_conf(PROVIDER)

def update_instances():

	# Wait until no instances are pending
	for instance in list_instances():
		print instance
		while instance.state == 'pending':
			print '\t', instance.state
			time.sleep(5)
			instance.update()
		print '\t', instance.state

	PROVIDER = get_provider_dict()
	for stage in PROVIDER['machines']:
		for name in PROVIDER['machines'][stage]:
			if 'id' in PROVIDER['machines'][stage][name]:
				id = PROVIDER['machines'][stage][name]['id']
				for instance in list_instances():
					if instance.__dict__['id'] == id:

						image_id    = instance.__dict__.get('image_id')
						placement   = instance.__dict__.get('placement')
						private_ip  = [instance.__dict__.get('private_ip_address')]
						private_dns = [instance.__dict__.get('private_dns_name')]
						public_ip   = [instance.__dict__.get('dns_name')]
						
						info = {
							'image'       : image_id,
							'placement'   : placement,
							'private_ip'  : private_ip,
							'private_dns' : private_dns,
							'public_ip'   : public_ip,
						}
						PROVIDER['machines'][stage][name].update(info)

	write_conf(PROVIDER)

def save_as_ami(name, region_id=None, arch='i386'):
	PROVIDER = get_provider_dict()
	if not region_id:
		region_id = PROVIDER['region_id']
	
	# Copy pk and cert to /tmp, somehow
	fabric.api.put(fabric.api.env.conf['AWS_X509_PRIVATE_KEY'], '/tmp/pk.pem')
	fabric.api.put(fabric.api.env.conf['AWS_X509_CERTIFICATE'], '/tmp/cert.pem')
	
	# Edit the sources list to include ec2 tools
	fabric.contrib.files.sed('/etc/apt/sources.list', 'universe$', 'universe multiverse', use_sudo=True)
	package_update()
	package_install('ec2-ami-tools', 'ec2-api-tools')
	
	# Bundle the volume
	fabric.api.sudo(
		'ec2-bundle-vol -c /tmp/cert.pem -k /tmp/pk.pem -u %s -s 10240 -r %s' % (
			fabric.api.env.conf['AWS_ID'], arch))
	fabric.api.sudo(
		'ec2-upload-bundle -b %s -m /tmp/image.manifest.xml -a %s -s %s --location %s' % (
			fabric.api.env.conf['AWS_AMI_BUCKET'], 
			_get_access_secret_keys(), 
			#fabric.api.env.conf['AWS_ACCESS_KEY_ID'], 
			#fabric.api.env.conf['AWS_SECRET_ACCESS_KEY'], 
			region_id))
	
	# Register the key
	result = fabric.api.sudo(
		'ec2-register -C /tmp/cert.pem -K /tmp/pk.pem --region %s %s/image.manifest.xml -n %s' % (
			region_id, 
			fabric.api.env.conf['AWS_AMI_BUCKET'], 
			name))
	
	# Remove the temp files
	fabric.api.run('rm /tmp/pk.pem')
	fabric.api.run('rm /tmp/cert.pem')
	
	# Return the ami object
	ami = result.split()[1]
	return ami
	
def launch_auto_scaling(stage='development', region_id=None):
	PROVIDER = get_provider_dict()
	if not region_id:
		region_id = PROVIDER['region_id']

	# Get connection
	conn = boto.ec2.autoscale.AutoScaleConnection(
			_get_access_secret_keys(), 
			#fabric.api.env.conf['AWS_ACCESS_KEY_ID'], 
			#fabric.api.env.conf['AWS_SECRET_ACCESS_KEY'], 
			host='%s.autoscaling.amazonaws.com' % region_id)
	
	# Get the autoscale dict
	for name, values in PROVIDER.get(stage, {}).get('autoscale', {}):

		# Check if group exists
		if any(group.name == name for group in conn.get_all_groups()):
			fabric.api.warn(fabric.colors.orange('Autoscale group %s already exists' % name))
			continue

		# Launch the configuration
		lc = boto.ec2.autoscale.LaunchConfiguration(
				name     = '%s-launch-config' % name, 
				image_id = values['image'], 
				key_name = PROVIDER['key'],
				)

		# Create the auto scaling group
		conn.create_launch_configuration(lc)
		ag = boto.ec2.autoscale.AutoScalingGroup(
				group_name         = name, 
				load_balancers     = values.get('load-balancers'), 
				availability_zones = [region_id], 
				launch_config      = lc, 
				min_size           = values['min-size'], 
				max_size           = values['max-size'],
				)
		conn.create_auto_scaling_group(ag)

		# Set the autoscaling trigger
		if 'min-cpu' in values and 'max-cpu' in values:
			tr = boto.ec2.autoscale.Trigger(
				name            = '%s-trigger' % name, 
				autoscale_group = ag, 
				measure_name    = 'CPUUtilization', 
				statistic       = 'Average', 
				unit            = 'Percent', 
				dimensions      = [('AutoScalingGroupName', ag.name)],
				period          = 60, 
				breach_duration = 60,
				lower_threshold = values['min-cpu'], 
				upper_threshold = values['max-cpu'], 
				lower_breach_scale_increment = '-1', 
				upper_breach_scale_increment = '2', 
				)
			conn.create_trigger(tr)

