# django-fab-deploy: django deployment tool

NOTE: This branch has been abandoned as of 6/20/2011, most of the functionality will be rolled into a new deployment tool under development.  For now, use builder or the master branch of red-fab-deploy.

red-fab-deploy is a collection of Fabric scripts for deploying and
managing django projects on Debian/Ubuntu servers. License is MIT.

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

Skip this section if you've never used fab-deploy before.

### Host Determination
I had to remove fab auto-detecting the hosts from your config file as it was just creating too many problems.  So just setup your hosts with 'fab setup_hosts' first.

### File name conventions

By default, configuration files for apache, nginx, and uwsgi must follow a very common naming
convention.  These files all should be found in the /deploy/ folder in side of
the project.  Simply put, the files must describe the stage by using the 
convention 'filename.<stage>.[ini|conf]', or be for any stage with 'filename.[ini|conf]'.

HOWEVER, you can specify an arbitrarily-named configuration file for many services using 'settings_file' in the 
services dictionary, explained below.

### Autoscaling
Currently only works for postgresql and web, although anything that doesn't need inter-server communication should be fine.
Autoscaling only works on EC2.  

IMPORTANT: Right now for postgres autoscaling to work, your clusters need to be named 'database' and 'web', with the correct
server_types (see below).

ALSO IMPORTANT: Postgres autoscaling may turn off the server that has your database on it.  Right now there is no backup system.
Make sure this is what you want to do.

### Backwards Compatibility
Every effort has been made to ensure backwards compatibility... but I'm sure something will be broken.  Sorry.

### Configuration File Changes
Configuration settings are now primarily stored in a python dictionary, instead of env.conf and a json file, although
those should continue to work for the near future.  Deprication warnings will be given.  See below for details.

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

## Older Method

I'm not sure how relevant these are, as we're really focusing on EC2 now.  But mostly this should still work.

TODO: clean this up.

### Development

There now exists a set of advanced tools for streamlining the setup of 
cloud servers and project deployment.  Follow these steps:

1. Ensure you have correctly set up your settings using the instructions above.

2. To begin with the set up of your cloud account you must run the following commands. On
AWS this will create a default key file and authorize tcp ports 22 and 80 for use. 

		$ fab generate_config
		$ fab go:development
		$ fab update_instances # might need to wait a minute and run this

3. You must wait until all your instances have spawned before going further.  This could take 
up to 5 minutes.

4. To install all the correct software on your new development instance run the following:

		$ fab -i deploy/[your private SSH key here] set_hosts:development go_setup:development

	This will grab all the development instance ip addresses, set them as hosts, and then run
	a software setup package on each of the servers based on the generated config file.

5. Next you want to deploy to the development server by running the following:

		$ fab -i deploy/[your private SSH key here] set_hosts:development go_deploy:development,tag

	This will put the trunk of your repo onto each machine with server software and make it active.
	Be aware that this will remove any current version of trunk that is currently deployed.

### Production

Production is almost identical to development, except for the following:

	$ fab generate_config # Do not overwrite an earlier file
	$ fab go:production
	$ fab update_instances # might need to wait a minute and run this
	$ fab -i deploy/[your private SSH key here] set_hosts:production go_setup:production
	$ fab -i deploy/[your private SSH key here] set_hosts:production go_deploy:production,tag

NOTE: If you already have generated a config for deployment DO NOT generate another config file.
This is very important as you may overwrite the original and lose the information you have inside
of it.  Furthermore, you'll want to check in the config file into your repository.

### Tools

If you are deploying on another host such as Rackspace you must run this next set of commands. 
 This will create a 
default key file, create and set up a user, add the user to the default security group, 
and then grant sudo access.  Finally, it will copy that key into the authorized_keys file for 
each machine you've created the user on.

	$ fab ssh_local_keygen:"development.key"
	$ fab set_hosts:development,root provider_as_ec2:username=ubuntu
	$ fab set_hosts:development,root ssh_authorize:username=ubuntu,key=deploy/development.key.pub

If the user is already created and has sudo access you can try this.

	$ fab ssh_local_keygen:"development.key"
	$ fab set_hosts:development,otheruser ssh_authorize:username=ubuntu,key=deploy/development.key.pub
	$ fab set_hosts:development,otheruser user_setup:otheruser
	$ fab -i deploy/[your private SSH key here] set_hosts:production,otheruser go_deploy:production,tag,otheruser
	$ fab -i deploy/[your private SSH key here] set_hosts:production,otheruser web_server_start

## Deploying on the Server

### The Code Manually

*If this is the first time* deploying on the server run the following:

	fab -i deploy/[your private SSH key here] dev deploy_full:"tagname"
    
Here "tagname" is the name of the tagged version of the code you wish
to deploy.  This code must reside in the /repo/tags/ directory.
If you have not created a tag yet, do it with::

	svn copy trunk tags/release-0.0.1; svn ci -m "Tagging 'trunk' for django-fab-deploy to work."

For the source code to be installed from the SVN repository to the 
server you need to enter your SVN credentials.

*If this is not the first time* you are deploying on the server then run:

	fab -i deploy/[your private SSH key here] dev deploy_project:"tagname" 
	fab -i deploy/[your private SSH key here] dev make_active:"tagname"

### The Server

*If this is the first time* deploying on the server run the following:

	* Edit deploy/uwsgi.ini and substitute 127.0.0.1 with the local IP address of the production machine.
	* Edit deploy/nginx.conf and substitute the 127.0.0.1 in the upstream django server with the local IP address and the 127.0.0.1 in the server_name with the remote IP address of the production machine.

Then launch:

	fab dev web_server_setup web_server_start -i deploy/[your private SSH key here]

	*If this is not the first time	* then just run::

	fab -i deploy/[your private SSH key here] dev uwsgi_restart
	fab -i deploy/[your private SSH key here] dev web_server_restart
  
Next you'll have to run the commands to have the application running, such as:

	fab -i deploy/[your private SSH key here] dev manage:syncdb 
	fab -i deploy/[your private SSH key here] dev manage:loaddata test

## Database Setup

The databases supported with red-fab-deploy are MySQL and PostgreSQL.

### Important Setup

By default red-fab-deploy will set to values inside of fabric.api.env.conf:

	DB        = 'mysql' # 'postgresql' is also allowed
	DB_PASSWD = 'password'

These indicate that the database type being used is 'mysql' and that the
database password for the root user is 'password'.  BE AWARE THAT THIS IS 
ENTIRELY INSECURE.  If you are installing any databases you should put the
'DB_PASSWD' setting inside your fabfile inside of the env.conf dictionary
and change the value from 'password' to something secure.  You can also set
this value to an empty string if you want to always be prompted for a 
password.

### MySQL Setup

To install and setup mysql you'll need to run the following commands::

	fab -i deploy/[your private SSH key here] dev mysql_install
	fab -i deploy/[your private SSH key here] dev mysql_create_db
	fab -i deploy/[your private SSH key here] dev mysql_create_user

### PostgreSQL

The PostgreSQL commands are not yet set up


## Autoscale Methodology

#TODO