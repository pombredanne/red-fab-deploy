#!/bin/bash

cd /srv/active
source env/bin/activate 
#fab settings:production localhost sync_data #TODO: test under database changes
fab cluster:web instance_type:autoscale settings:production setup_hosts update_db_servers #TODO: dynamic cluster names
fab cluster:database instance_type:template settings:production setup_hosts service:postgresql,stop
sleep 60
fab cluster:database instance_type:master settings:production setup_hosts service:postgresql,stop