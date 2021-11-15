#!/bin/bash
set -eou pipefail

# Setup a config for our mysql db.
cp -vf "${CONFIG_FILE}" conf/config
sed -i "s;YOUR_AUR_ROOT;$(pwd);g" conf/config

# Setup Redis for FastAPI.
sed -i 's|^cache = [^1].*|cache = redis|' conf/config
sed -ri 's|^(redis_address) = .+|\1 = redis://redis|' conf/config

if [ ! -z ${COMMIT_HASH+x} ]; then
    sed -ri "s/^;?(commit_hash) =.*$/\1 = $COMMIT_HASH/" conf/config
fi

rm -rf $PROMETHEUS_MULTIPROC_DIR
mkdir -p $PROMETHEUS_MULTIPROC_DIR

exec "$@"
