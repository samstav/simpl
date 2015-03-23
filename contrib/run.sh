#! /bin/bash

echo "Fetching environment..."

/usr/bin/python /app/bootstrap.py

echo "Setting environment in etcd..."

/bin/crypt set \
-endpoint="http://192.168.59.103:4001" \
-keyring="/app/pubring" \
/app/checkmate/staging/environment .env

echo "Environment set."
exit 0
