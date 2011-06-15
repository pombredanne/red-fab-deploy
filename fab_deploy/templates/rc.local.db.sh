#!/bin/bash

cd /srv/active
source env/bin/activate
fab settings:production localhost sync_data
fab cluster:web instance_type:autoscale settings:production update_db_servers #TODO: dynamic cluster names
fab cluster:db instance_type:master settings:production service_postgresql:stop