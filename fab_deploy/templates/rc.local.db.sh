#!/bin/bash

cd /srv/active
source env/bin/activate
fab settings:production sync_data
fab cluster:web settings:production update_db_servers #TODO: dynamic cluster names
fab cluster:db instance_type:master settings:production service_postgresql:stop