#!/usr/bin/bash
set -e

# Get needed data.
commit_hash="$(git rev-parse --short HEAD)"
fastapi_secret="$(openssl rand -hex 32)"

# Set up config files.
echo "+ Setting up config files..."

sed -i \
    -e "s|user =.*|user = mpr|" \
    -e "s|password =.*|password = ${mpr_db_password}|" \
    -e 's|^name =.*|name = mprweb|' \
    -e "s|aur_location =.*|aur_location = https://${mpr_url}|" \
    -e "s|git_clone_uri_anon =.*|git_clone_uri_anon = https://${mpr_url}/%s.git|" \
    -e "s|git_clone_uri_priv =.*|git_clone_uri_priv = ssh://mpr@${mpr_url}/%s.git|" \
    -e "s|smtp-server =.*|smtp-server = ${hw_url}|" \
    -e 's|smtp-port =.*|smtp-port = 465|' \
    -e 's|smtp-use-ssl =.*|smtp-use-ssl = 1|' \
    -e 's|smtp-user =.*|smtp-user = mpr@hunterwittenborn.com|' \
    -e "s|smtp-password =.*|smtp-password = ${mpr_smtp_password}|" \
    -e 's|sender =.*|sender = mpr@hunterwittenborn.com|' \
    -e 's|reply-to =.*|reply-to = mpr@hunterwittenborn.com|' \
    -e 's|Ed25519 =.*|Ed25519 = SHA256:8A1Asmd6rEtypl+h1WM/3Jgonauwx6Hez5FaytLFdwY|' \
    -e 's|ECDSA =.*|ECDSA = SHA256:7Wki/ZTENAVOYmAtH4+vhqZB8vHkLURS+eK1SQy0jTs|' \
    -e 's|RSA =.*|RSA = SHA256:bAWQvVgBKyuUn8acQIrEQ7Hh1PTXjghXSYovSWhrh7Y|' \
    -e "s|ssh-cmdline =.*|ssh-cmdline = ssh mpr@${mpr_url}|" \
    -e "s|commit_hash =.*|commit_hash = ${commit_hash}|" \
    -e "s|session_secret =.*|session_secret = ${fastapi_secret}|" \
    -e 's|YOUR_AUR_ROOT|/aurweb|' \
    conf/config.defaults

rm conf/config.dev
cp conf/config.defaults conf/config.dev

cp logging.prod.conf logging.conf

echo "+ Building image..."
docker-compose build --pull --no-cache mprweb-image

echo "+ Deploying..."
cd /var/www/mpr.hunterwittenborn.com
docker-compose -f ./docker-compose.yml \
               -f ./docker-compose.override.yml \
               down

find ./ -maxdepth 1 \
        -not -path './' \
        -not -path './data' \
        -not -path './service.sh' \
        -exec rm -rf '{}' +

cd -
find ./ -maxdepth 1 \
        -not -path './' \
        -not -path './data' \
        -not -path './service.sh' \
        -exec cp '{}' '/var/www/mpr.hunterwittenborn.com/{}' -R \;

cd /var/www/mpr.hunterwittenborn.com
docker-compose -f ./docker-compose.yml \
               -f ./docker-compose.override.yml \
               -f ./docker-compose.mpr.yml \
               up -d nginx
