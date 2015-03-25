#! /bin/bash

echo "Fetching environment..."

python /app/bootstrap.py

echo "Setting environment in etcd..."

/bin/crypt set \
-endpoint="http://etcd:4001" \
-keyring="/app/pubring" \
/app/checkmate/staging/environment .env

echo "Environment set."
exit 0
