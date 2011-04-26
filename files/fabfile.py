"""
fab deployment script
====================================

"""
import os
from fabric.api import *
from fab_deploy import *

def my_site():
    """ Default Configuration """
    env.conf = dict(
        PROVIDER              = '%(PROVIDER)s',
        AWS_ACCESS_KEY_ID     = '%(AWS_ACCESS_KEY_ID)s',
        AWS_SECRET_ACCESS_KEY = '%(AWS_SECRET_ACCESS_KEY)s',
		CONF_FILE             = os.path.join(os.getcwd(),'fabric.conf'),
		INSTANCE_NAME         = '%(INSTANCE_NAME)s', # Recommend no underscores
        REPO                  = '%(REPO)s',
    )

my_site()

