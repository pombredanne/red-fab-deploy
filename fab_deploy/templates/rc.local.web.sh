#!/bin/bash

# Get all db hosts properly
cd /srv/active
source env/bin/activate
fab settings:production localhost update_db_servers