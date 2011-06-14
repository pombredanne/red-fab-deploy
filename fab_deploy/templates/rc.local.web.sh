#!/bin/bash

# Get all db hosts properly
cd /srv/active
source env/bin/activate
fab -f fabfile.py settings:config.production localhost update_db_servers