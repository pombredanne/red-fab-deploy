#!/bin/bash

cd /srv/active
source env/bin/activate
fab cluster:web instance_type:autoscale settings:production update_db_servers #TODO: dynamic cluster names
fab settings:production sync_data
fab settings:production cluster:db instance_type:master service_postgresql:stop