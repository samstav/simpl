#! /bin/bash

echo "Passing arguments to supervisor's config..."

ROLE=$@

sed -i "s,REPLACEME,$ROLE,g" /etc/supervisor.d/checkmate.conf

touch /var/log/checkmate-stdout.log
tail -f /var/log/checkmate-stdout.log&

echo "Starting Supervisor..."

SUPERVISOR_CMD="supervisord -n -c /etc/supervisord.conf"

if [ $LOAD_ENV_FROM_ETCD ]
then
    exec /app/docker/config/envfromjson.py \
    -f <(crypt get -endpoint=$ETCDCTL_PEERS -secret-keyring="/etc/configs/secring.gpg" /app/checkmate/$PREFIX/environment) -- \
    $SUPERVISOR_CMD
else
    exec $SUPERVISOR_CMD
fi
