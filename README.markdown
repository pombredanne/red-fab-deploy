# red-fab-deploy: django deployment tool

red-fab-deploy is a collection of Fabric scripts for deploying and
managing django projects on Debian/Ubuntu servers. License is MIT.

Maintainer: Chris Gilmer at FF0000

This project is specifically targeted at deploying websites built using
the `pypeton <https://github.com/ff0000/pypeton>` project creation tool.
Basically this means you must follow the same folder and file layout as
found in that tool.  Generally, at least.
(The most important thing is to have your manage.py and django apps in a /project subfolder).

This project was inspired by `django-fab-deploy <http://packages.python.org/django-fab-deploy>`
and `cuisine <https://github.com/ff0000/cuisine/>`.

These tools are being geared towards deploying on Amazon EC2.

## Installation

IMPORTANT: red-fab-deploy will only work if you install the following packages:
    
	$ pip install fabric>=1.0
	$ pip install boto==2.0b4
    	$ pip install simplejson
    
To use autoscaling, you'll need to have the AutoScaling and CloudWatch apis installed on your local system.
If you don't have a native package, they can be found at:

    http://ec2-downloads.s3.amazonaws.com/AutoScaling-2010-08-01.zip
    http://ec2-downloads.s3.amazonaws.com/CloudWatch-2010-08-01.zip

## Release Notes

This software is beta quality at best.  It is not fully backwards compatible with earlier versions of red-fab-deploy, and postgresql autoscaling does not work all of the time.

There will be other bugs too.

### Configuration File Changes & Backwards Compatibility
Configuration settings are now primarily stored in a python dictionary, instead of env.conf and a json file.  Some of the documentation below advertises backwards compatibility for RFD json conf files.  This does not actually work correctly; it will overwrite your conf file and remove some of the information.

### Autoscaling
Currently only fully works generic/web clusters that don't need inter-server communication.  Only will ever work on EC2.

#### Postgresql Autoscaling: Further notes.
Postgresql Autoscaling does not work correctly all of the time.  Pgpool is difficult and possibly a bad choice for this project.  Even if it does work, there are two important caveats:

* Your clusters need to be named 'database' and 'web', with the correct server_types (see below).
* Postgres autoscaling may turn off the server that has your database on it.  Right now there is no automatic backup.  Make sure this is what you want to do.


### Host Determination
I had to remove fab auto-detecting the hosts from your config file as it was just creating too many problems.  So just setup your hosts with 'fab setup_hosts' first.

### File name conventions

By default, configuration files for apache, nginx, and uwsgi must follow a very common naming
convention.  These files all should be found in the /deploy/ folder in side of
the project.  Simply put, the files must describe the stage by using the 
convention 'filename.<stage>.[ini|conf]', or be for any stage with 'filename.[ini|conf]'.

HOWEVER, you can specify an arbitrarily-named configuration file for many services using 'settings_file' in the 
services dictionary, explained below.


## Configuration

### Fabfile

If you've used fabric before, you know about fabfiles.  This is where fabric finds the commands
it will run.  You should have this at the root of your project, and called 'fabfile.py',
for it to be automatically found;
otherwise you will have to specify it with -F when running fab.

The only thing your fabfile needs to have is:

    from fabric.api import *
    from fab_deploy import *
    env.settings_prefix = 'project.settings.'

The env.settings_prefix is optional, put wherever your settings files will live, relative to your fabfile.
This will prevent you from having to specify the full path every time.
You can also put any commands in here that are specific to your project.  More on that below.

### Settings

As with earlier versions of red-fab-deploy, you can specify settings via env.conf settings
in the fabfile (see fabfile-example.py for, um, an example),
and via a fabric.conf json file.  However the new, recommended way is by using a per-stage python dictionary.
This allows for greater flexibility and organization.

What does this mean?  It means you have a python module, it could be your django settings file, with a dictonary in it. 
One dictionary per stage.  By default this dictionary is called DEPLOY.  For example, to specify a settings file called 'production'
in your env.settings_prefix, with a settings dictionary called DEPLOY, you would call:

    fab settings:production command_to_run

To specify a different settings file, with a settings dictionary called, say, 'fab_deploy_settings', you could call:

    fab settings:some.path.to.another.settings.file.fab_deploy_settings
    
Fab-deploy is smart enough to figure out what you're trying to do.

#### Settings Dictionary Options

The settings dictionary can contain the following options.  Those with defaults are optional.  
(AS only) means that the option is only required/used by autoscaling.  Always use absolute paths.

* project_name - name of the project, used in directory structures and log messages
* repo - The VCS repo the project lives at
* vcs (default: svn) - The VCS system to use.  Currently only svn and git are supported.
* vcs_tags (default: /tags) - Where in the repo to find tagged versions for deployment.

* local_project_root (AS only) - Where your project lives.  Used to figure out relative paths for deployment.

* stage - the stage this dictionary represents (could be 'production')
* data_file - where to store data about created AWS instances for later lookup.  Will be in json format.

* key_name - AWS name of key to use for creating new instances
* key_location - Where the key lives on your hard drive, for logging in to new instances.  Will be passed to fab.

* region - AWS region, like 'us-west-1'
* availability_zone - AWS availability zone, like 'us-west-1c'

* aws_access_key_id - Your AWS Public Key
* aws_secret_access_key - Your AWS Private Key
* aws_x509_certificate (AS only) - Path to your AWS Public Certificate File 
* aws_x509_private_key (AS only) - Path to your AWS Private Certificate File
* aws_id (AS only) - Your aws user id, should look like 1234-5678-9123 (at the very bottom of the webpage that has your keys and certs)

* ami_bucket (AS only) - S3 bucket to store files related to saved AMIs.  Doesn't have to already exist.

* clusters - a dictionary specifying what sorts of machines to deploy.  Explained below.

#### Clusters Options
The clusters sub-dictionary is like the old fabric.conf file.  It explains to fab-deploy what servers you want to start up,
what services they should have, etc.  The difference here is that you're organizing your machines by type (web server, db server, etc).
Remember the whole settings dictionary is for a given stage, so all of these clusters
will be as well.

Each cluster is a name:options pair, where 'name' is the name of the cluster, and 'options' is the cluster options.  So:

    'clusters': {
        'database_cluster': {'option1': 'value1', ... },
        'web_cluster': {'optionA': 'valueA', ... }
     }
     
Cluster options are:

* autoscale (default: False) - Should this cluster autoscale?
* server_type (somewhat optional but untested) - either fab_deploy.constants.SERVER_TYPE_DB or fab_deploy.constants.SERVER_TYPE_WEB
* size - EC2 machine size to use, like 'm1.small'
* initial_image ('image' is also acceptable) - AMI to use when creating instance
* services - a dictionary of name:options pairs for services to install and setup on the instance, enumerated below.  
* post_setup (optional) - a string specifying a function to run after setup is complete, for example 'fabfile.web_post_setup'
would run a function called web_post_setup() in fabfile.py.  This is where you would install extra packages, for example.
* post_activate (optional) - a string specifying a function to run after make_active is complete.  This is where you would recreate
your search index, for example.
* with_db_cluster (AS only, fab_deploy.constants.SERVER_TYPE_WEB clusters only) - Linked db cluster name
* with_web_cluster (AS only, fab_deploy.constants.SERVER_TYPE_DB clusters only) - Linked web cluster name

If autoscale is True, the following options are also available:
* cpu_range - a 2-element tuple/list of the minimum and maximum allowed CPU range before autoscaling grows or shrinks the cluster.
* count_range - a 2-element tuple/list of the minimum and maximum allowed number of instances in the autoscaling cluster.
* load_balancer (optional - a dictonary of options
to create a load balancer (if not given no load balancer will be created for the autoscaling cluster):
	* name - the name of the load balancer
	* cookie_name (optional) - the external cookie to hook on, repeated visits with the same cookie value will always go to the same instanace.
In Django it is 'sessionid'.
	* listeners - a list of dictionaries that the load balancer should listen on, like [{'port': 80, 'protocol': 'HTTP'}].  Both port and protocol are required.
	* target - the EC2 load balancer's health check protocol and port, like 'HTTP:80/'.

If autoscale is False, the following options are available:
* count (default: 1) - number of instances to start in this cluster

#### Available Services

The following services are available.  Specify them like 'name': {options} in the services dictionary above.

TODO: this is only a partial list of services AND options

* postgresql
	* name - Database name
	* user
	* password
	* ebs_size (default: disabled)
	* support_pgpool (default: False)
* nginx
	* settings_file (default as specified in release notes above) - RELATIVE PATH of the settings file to use
* uwsgi
	* settings_file (default as specified in release notes above) - RELATIVE PATH of the settings file to use
* pgpool
	* password - password to use for pgpool to connect for health check.  TODO: More info on this later
* postgresql-client (no options available)
* s3fs
	* bucket - bucket to mount
	* mountpoint - where to mount it

An example file will be available soon.

## Deployment - New Method

We'll assume for this tutorial that you're interested in deploying your production stage, and that your settings are 
in the 'production' module as described above.  Substitute in appropriate values for your circumstances.

If you're using a json conf file, instead of using 'settings' to define your settings file, which in turn defines your stage... just use stage:<stagename>.

For now, you have to run setup_hosts after providing configuration and settings, to set the fabric hosts.  There's
not really a good way around this.

1. Log on to AWS, create a key, and download it.  Put the relevant information in your settings file.

2. To start instances, run:

    $ fab settings:production setup_hosts go_start

3a. If using autoscale, you'll have to setup (load software on) the master instance first.  The easiest way to do this is:

    $ fab settings:production setup_hosts go_setup_autoscale_masters go_setup_autoscale_templates
    
3b.  Otherwise you can just do:
   
    $ fab settings:production setup_hosts go_setup
    
4. To deploy your software on the hosts, and set it as active, run:

    $ fab settings:production setup_hosts go_deploy_tag:my_tag_name
    
    This command also takes the arguments 'force', 'use_existing', and 'full'.
    
If you're not autoscaling, you're done!  Otherwise...

5.  To save your templates and prepare to launch autoscale groups, run

    $ fab settings:production setup_hosts go_save_templates
    
6.  To use these templates to launch autoscale groups, run

    $ fab settings:production setup_hosts go_launch_autoscale

    This command also takes the arguments 'force' and 'use_existing'.
    Note that this command will not remove an existing load balancer under any circumstances, to avoid breaking a live site.
    
### A few other commands

* 'go_stop_autoscale' will stop your autoscaling clusters.  You can specify only certain clusters with the argument 'clusters'.
Note that this does not stop the masters or templates, or delete static IPs or load balancers, you'll have to do that through the web
interface for now.

* 'clusters', 'stage', 'server_types', 'instance_types' - all can be run before setup_hosts (or as options TO setup_hosts).
These allow filtering of the instances so you can run specific commands.
Server Types are 'web', 'db', and None, or whatever you specify manually in your cluster configuration.  Instance Types 
are 'master', 'template', 'autoscale', and None.

* 'setup_hosts' will find all instances, including those started with autoscale.
