#!/bin/bash

cd /srv/active
source env/bin/activate
fab -f fabfile.py settings:config.production autoscaling_web_servers update_db_servers
fab -f fabfile.py settings:config.production sync_data
fab -f fabfile.py settings:config.production original_master service_postgresql:stop