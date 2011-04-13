#!/bin/bash

# Get all db hosts properly
fab -f /srv/active/fabfile.py oldest_other_webserver steal_config_file:/etc/pgpool.conf
service pgpool2 restart