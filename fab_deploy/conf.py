from fab_deploy.constants import PROVIDER_DICT
from fab_deploy.utils import combine, setup_hosts, update_env
from fabric import colors
from fabric.api import env, prompt
from fabric.contrib import console
from fabric.utils import abort
import os
import simplejson
import sys

CLUSTER_DEFAULTS = {
    'size': 'm1.small',
}

def settings(settings_module):
    ''' 
    Load python dictionary with settings in it.
    Call with a module with a DEPLOY variable in it, or with a fully qualified name of a deploy dictionary 
    For example, "settings.production" and "settings.production.DEPLOY" are equivalent.
    If env.settings_prefix is defined, it is prefixed to the start of the settings module.  If this fails, the settings_module is tried normally.
    '''
    
    sys.path.insert(0, '')
    sys.path.insert(1, '/srv/active')
    
    attempts = []

    if hasattr(env, 'settings_prefix'):
        attempts += [env.settings_prefix + settings_module + '.DEPLOY', 
                     env.settings_prefix + settings_module]
    attempts += [settings_module + '.DEPLOY',
                 settings_module]
    
    for attempt in attempts:
        try:
            env.fab_deploy_settings = import_string(attempt)
            fab_config.load()
            fab_data.load()
            setup_hosts()
            return
        
        except ImportError, AttributeError:
            pass
    
    abort(colors.red('Settings not found.'))
    
def import_string(string):
    if string is None:
        return lambda: None
    mod, func = string.rsplit('.', 1)
    __import__(mod)
    return getattr(sys.modules[mod], func)
    
class FabDeployConfig(object):
    
    '''
    Config object, maintaining backwards compat with old config method.  Lazy loading.
    
    This is distinguished from 'data': 'config' is user-set settings, 'data' is deployment information that is saved BY rfd.
    
    Can load config info from:
        * env.conf['CONF_FILE'] - A json-formatted conf-and-data file such as used in rfd 0.1.
        * env.fab_deploy_settings - A python dictionary of settings, many with the same or similar keys as the old-school conf file
            - Maintains backwards compat by aliasing these settings into env.conf and get_provider_dict if needed
    '''
    
    # comapt maps, as [new, old]
    env_conf_settings_map = [
                ['project_name', 'INSTANCE_NAME'],
                ['aws_access_key_id', 'AWS_ACCESS_KEY_ID'],
                ['aws_secret_access_key', 'AWS_SECRET_ACCESS_KEY'],
                ['data_file', 'CONF_FILE'],
                #['provider', 'PROVIDER'], #NO LONGER USED
                ['repo', 'REPO'],
                ['vcs', 'VCS'],
                ['vcs_tags', 'VCS_TAGS']]
    
    json_conf_settings_map = [
                ['key_name', 'key'], #TODO: key_location
                ['availability_zone', 'location'],
                ['region', 'region_id']]
    
    def __init__(self):
        self._config = None
        self._compat = None
        self.from_json_file = False
        self.from_python_settings = False
        
    def load(self):
        self._config = {}
        self._compat = {}
        
        # Merge together dat from different files
        if hasattr(env, 'conf') and 'CONF_FILE' in env.conf:
            self.load_json_conf_file(env.conf['CONF_FILE'])
        
        if hasattr(env, 'fab_deploy_settings'):
            self.load_python_settings(env.fab_deploy_settings)
            
        for settings in self.config['clusters'].values():
            for default, value in CLUSTER_DEFAULTS.iteritems():
                if default not in settings:
                    settings[default] = value
            
        update_env()
        
    def _get_config(self):
        if self._config is None:
            self.load()
        return self._config
            
    def _set_config(self, config):
        self._config = config
        
    def _get_compat(self):
        if self._compat is None:
            self.load()
        return self._compat
            
    def _set_compat(self, compat):
        self._compat = compat
            
    config = property(_get_config, _set_config) 
    compat = property(_get_compat, _set_compat)                       
                                              
    def load_json_conf_file(self, filename):
        self.from_json_file = True
        json_config = simplejson.loads(open(filename,'r').read())
        
        # Maintain forwards-compat with env.conf
        if hasattr(env, 'conf'):
            for deploy_setting, env_conf_setting in self.env_conf_settings_map:
                if env_conf_setting in env.conf:
                    self._config[deploy_setting] = env.conf[env_conf_setting]
                
        # Maintain forwards-compat with json conf
        for deploy_setting, json_conf_setting in self.json_conf_settings_map:
            if json_conf_setting in json_config:
                self._config[deploy_setting] = self._compat[json_conf_setting] = json_config.pop(json_conf_setting)
        
        self._compat['machines'] = json_config.pop('machines')
        # clusters maintained in __getitem__ below for runtime compat check
        
        self._config.update(json_config)
            
    def load_python_settings(self, settings):
        self.from_python_settings = True

        if 'stage' not in settings:
            raise Exception('You must specify a stage in the settings.')

        env.stage = settings['stage']
        
        self._config.update(settings)
        
        # Add key name
        if 'key_location' in settings:
            env.key_filename = [settings['key_location']]

        # Maintain backwards-compat with env.conf
        env.conf = getattr(env, 'conf', {})
        for deploy_setting, env_conf_setting in self.env_conf_settings_map:
            if deploy_setting in settings:
                env.conf[env_conf_setting] = settings[deploy_setting]
        
        #TODO: what to do with these?
        env.conf.update({
            'FILES': os.path.join(os.path.dirname(__file__), 'templates'),
            'ENV_DIR': '/srv/active/env/',
            'SRC_DIR': os.path.join('/srv', self._config['project_name']),
        })

        # Maintain backwards compat with GET_PROVIDER_DICT
        
        for deploy_setting, json_conf_setting in self.json_conf_settings_map:
            if deploy_setting in settings:
                self._compat[json_conf_setting] = settings[deploy_setting]
        
        self._compat['machines'] = {settings['stage']: settings['clusters']}
        
    def cluster(self, cluster):
        return self.config['clusters'][cluster]
    
    # Dictionary access methods
    
    def __len__(self):
        return self.config
    
    def __contains__(self, item):
        return item in self.config

    def __getitem__(self, key):
        # Friendly compat
        if key == 'clusters' and self.from_json_file:
            if not hasattr(env, 'stage'):
                abort('You need to call stage=[stage] or another method that sets env.stage before using this method')
            self.config['clusters'] = self.compat['machines'][env.stage]
        return self.config[key]
    
    def __setitem__(self, key, value):
        self.config[key] = value
    
    def __delitem__(self, key):
        del self.config[key]
        
    def get(self, key, default=None):
        return self.config.get(key, default)
    
    def has_key(self, key):
        return self.config.has_key(key)
    
class FabDeployData(object):
    
    ''' 
    Data object, maintaining backwards compat with old config method.  Lazy loading.
    
    This is distinguished from 'config': 'config' is user-set settings, 'data' is deployment information that is saved BY rfd.
    
    Can load/save data from/to:
        * env.conf['CONF_FILE'] - A json-formatted conf-and-data file such as used in rfd 0.1.
        * A FabDeployConfig instance with ['data_file'] - Same format for now, pending a decision where to store this data
        
    '''
    
    def __init__(self):
        self._data = None
        self.filename = None
        
    def __del__(self):
        if self._data is not None:
            self.write_json_data()
        
    def load(self):
        self._data = {}
        
        # Merge together data from different files
        if hasattr(env, 'conf') and 'CONF_FILE' in env.conf:
            self.load_json_data(env.conf['CONF_FILE'])
        
        if 'data_file' in fab_config:
            self.load_json_data(fab_config['data_file'])
            
    def _get_data(self):
        if self._data is None:
            self.load()
        return self._data
            
    def _set_data(self, data):
        self._data = data

    data = property(_get_data, _set_data)

    def load_json_data(self, filename):
        self.filename = filename
        if not os.path.isfile(filename):
            return
        self.data.update(simplejson.loads(open(filename,'r').read()))
        
    def write_json_data(self):
        import simplejson
        obj = simplejson.dumps(self.data, sort_keys=True, indent=4)
        f = open(self.filename, 'w')
        f.write(obj)
        f.close()

    def cluster(self, cluster):
        self.data['clusters'] = self.data.get('clusters', {})
        self.data['clusters'][cluster] = self.data['clusters'].get(cluster, {})
        return self.data['clusters'][cluster]
    
    # Dictionary access methods

    def __len__(self):
        return self.data
    
    def __contains__(self, item):
        return item in self.data

    def __getitem__(self, key):
        return self.data[key]
    
    def __setitem__(self, key, value):
        self.data[key] = value
    
    def __delitem__(self, key):
        del self.data[key]
        
    def get(self, key):
        return self.data.get(key)
    
    def has_key(self, key):
        return self.data.has_key(key)
    
fab_config = FabDeployConfig()
fab_data = FabDeployData()

### Backwards compatibility methods ###
def get_provider_dict():
    """ Get the dictionary of provider settings """
    return combine(fab_config.config, fab_config.compat, fab_data.data) 

def write_conf(instance,filename=''):
    """ Overwrite the conf file with dictionary values """
    fab_data.data = instance
    return fab_data.write_json_data()

def generate_config(provider='ec2_us_east'):
    """ Generate a default json config file for your provider """
    conf_file = env.conf['CONF_FILE']
    if os.path.exists(conf_file):
        if not console.confirm("Do you wish to overwrite the config file %s?" % (conf_file), default=False):
            conf_file = os.path.join(os.getcwd(), prompt('Enter a new filename:'))

    write_conf(PROVIDER_DICT[provider],filename=conf_file)
    print colors.green('Successfully generated config file %s' % conf_file)
    