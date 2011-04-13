#!/bin/bash

source /srv/active/env/bin/activate
fab -f /srv/active/fabfile.py autoscaling_webservers register_db_server:`curl http://169.254.169.254/latest/meta-data/public-hostname`
fab -f /srv/active/fabfile.py sync_data
fab -f /srv/active/fabfile.py original_db_master service_postgresql:stop