SERVER_TYPE_WEB = 'web'
SERVER_TYPE_DB = 'db'

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
