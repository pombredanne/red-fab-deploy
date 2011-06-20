#--- Deployment
from fab_deploy.machine import (generate_config,
	ec2_create_key, ec2_authorize_port,
	print_instance,  print_image,  print_size,  print_region,
	print_instances, print_images, print_sizes, print_regions,
	create_instance, deploy_instances, update_instances, save_as_ami)

from fab_deploy.deploy import (go, go_setup, go_deploy,
	deploy_full, deploy_project,
	make_src_dir, make_active, link_host, undeploy)

from fab_deploy.virtualenv import (pip, pip_install, pip_update,
	virtualenv_create, virtualenv)

#--- Linux
from fab_deploy.crontab import (crontab_set, crontab_add, crontab_show,
	crontab_remove, crontab_update)

from fab_deploy.file import link_exists, link, unlink, readlink

from fab_deploy.package import package_install, package_update, package_upgrade, \
	package_add_repository

from fab_deploy.system import (service, 
	get_public_ip, get_internal_ip, print_hosts, set_hostname, get_hostname,
	prepare_server, setup_backports, install_common_packages,
	usage_disk, usage_mem, usage_cpu, usage_system,)

from fab_deploy.user import (provider_as_ec2,
	user_exists, user_create, user_setup,
	group_exists, group_create,
	group_user_exists, group_user_add,
	ssh_keygen, ssh_local_keygen, ssh_get_key, ssh_authorize,
	grant_sudo_access,)

from fab_deploy.utils import (update_env, set_hosts, delete_pyc, debug_env, detect_os)

#--- Django
from fab_deploy.django_commands import (migrate, manage, syncdb,
	compress, test, syn)

#--- Media
from fab_deploy.media import (media_rsync, media_chown, media_chmod, media_sync)

#--- Servers
from fab_deploy.server import *

#--- Databases
from fab_deploy.db import *

#--- Version Control
from fab_deploy.vcs import *

from fab_deploy.conf import *

# --- This horror will be fixed soon
from fab_deploy.utils import *
from fab_deploy.autoscale import *
from fab_deploy.django_commands import *
