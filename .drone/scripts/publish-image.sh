#!/usr/bin/bash
set -ex

# Set up env file.
sed -i \
    -e "s|DB_PASSWORD='mpr'|DB_PASSWORD='${MPR_DB_PASSWORD}'|" \
    -e "s|AURWEB_FASTAPI_PREFIX='https://localhost:8444'|AURWEB_FASTAPI_PREFIX='https://${mpr_url}'|" \
    conf/docker.env

cd /var/www/mpr.hunterwittenborn.com
docker-compose down
find ./ -maxdepth 1 \
        -not -path './data' \
        -exec rm -rf '{}' +

cd -
find ./ -maxdepth 1 \
        -not -path './data' \
        -not -path './.git' \
        -exec cp '{}' '/var/www/mpr.hunterwittenborn.com/{}' -R \;

cd /var/www/mpr.hunterwittenborn.com
docker-compose build aurweb-image
docker-compose up -d nginx
