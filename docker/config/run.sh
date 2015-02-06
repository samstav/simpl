#! /bin/bash

echo "Passing arguments to supervisor's config..."

ROLE=$@

sed -i "s,REPLACEME,$ROLE,g" /etc/supervisor.d/checkmate.conf

touch /var/log/checkmate-stdout.log
tail -f /var/log/checkmate-stdout.log&

echo "Starting Supervisor..."

exec supervisord -n -c /etc/supervisord.conf
