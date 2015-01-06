#! /bin/bash

echo "Passing arguments to supervisor's config..."

ROLE=$@

sed -i "s,REPLACEME,$ROLE,g" /etc/supervisor.d/checkmate.conf

echo "Starting Supervisor..."

supervisord -c /etc/supervisord.conf &

sleep 5

echo "Tailing Checkmate logs"
tail -f /var/log/checkmate-stdout.log
