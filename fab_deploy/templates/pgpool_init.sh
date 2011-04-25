#!/bin/sh

### BEGIN INIT INFO
# Provides:          pgpool
# Required-Start:    $all
# Required-Stop:     $all
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: starts the pgpool server
# Description:       starts pgpool server using start-stop-daemon
### END INIT INFO

# From http://library.linode.com/web-servers/nginx/python-uwsgi/reference/init-deb.sh

PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
DAEMON=/usr/local/bin/pgpool

OWNER=root

NAME=pgpool
DESC=pgpool

test -x $DAEMON || exit 0

set -e

DAEMON_OPTS="-c -f /etc/pgpool.conf"

case "$1" in
  start)
        echo -n "Starting $DESC: "
        while [ ! "`pidof pgpool`" ]; do
            start-stop-daemon -o --start --chuid $OWNER:$OWNER --user $OWNER \
                --exec $DAEMON -- $DAEMON_OPTS
            sleep 1
        done
        echo "Done."
        ;;
  stop)
        echo -n "Stopping $DESC: "
        start-stop-daemon --signal 3 --quiet --retry 2 --stop \
                --exec $DAEMON
        echo "Done."
        ;;
  reload)
        $DAEMON $DAEMON_OPTS reload
        ;;
  force-reload)
        killall -15 $DAEMON
       ;;
  restart)
        echo -n "Restarting $DESC: "
        start-stop-daemon -o --signal 3 --quiet --retry 2 --stop \
                --exec $DAEMON
        sleep 1
        while [ ! "`pidof pgpool`" ]; do
            start-stop-daemon -o --start --chuid $OWNER:$OWNER --user $OWNER \
                --exec $DAEMON -- $DAEMON_OPTS
            sleep 1
        done
        echo "Done."
        ;;
  status)  
        killall -10 $DAEMON
        ;;
      *)  
            N=/etc/init.d/$NAME
            echo "Usage: $N {start|stop|restart|reload|force-reload|status}" >&2
            exit 1
            ;;
    esac
    exit 0