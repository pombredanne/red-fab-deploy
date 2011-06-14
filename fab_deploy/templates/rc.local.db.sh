#!/bin/bash

cd /srv/active
source env/bin/activate
fab settings:production autoscaling_web_servers update_db_servers
fab settings:production sync_data
fab settings:production original_master service_postgresql:stop