#!/bin/bash

source /srv/active/env/bin/activate
fab -f /srv/active/fabfile.py autoscaling_web_servers update_db_servers
fab -f /srv/active/fabfile.py sync_data
fab -f /srv/active/fabfile.py original_master service_postgresql:stop