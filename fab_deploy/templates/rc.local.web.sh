#!/bin/bash

# Get all db hosts properly
source /srv/active/env/bin/activate
fab -f /srv/active/fabfile.py localhost update_db_servers