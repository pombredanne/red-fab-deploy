#!/bin/bash

source /srv/active/env/bin/activate
# Get all db hosts properly
fab -f /srv/active/fabfile.py localhost update_db_servers
service pgpool2 restart