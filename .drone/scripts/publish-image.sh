#!/usr/bin/bash
set -e

# Get needed data.
commit_hash="$(git rev-parse --short HEAD)"
fastapi_secret="$(openssl rand -hex 32)"

# Set up config files.
echo "+ Setting up config files..."

sed -i \
    -e "s|AURWEB_FASTAPI_PREFIX='https://localhost:8444'|AURWEB_FASTAPI_PREFIX='https://${mpr_url}'|" \
    -e "s|CONFIG_FILE='conf/config.dev'|CONFIG_FILE='conf/config.defaults'|" \
    conf/docker.env

sed -i \
    -e "s|password =.*|password = ${mpr_db_password}|" \
    -e "s|aur_location =.*|aur_location = https://${mpr_url}|" \
    -e "s|git_clone_uri_anon =.*|git_clone_uri_anon = https://${mpr_url}/%s.git|" \
    -e "s|git_clone_uri_priv =.*|git_clone_uri_priv = ssh://mpr@${mpr_url}/%s.git|" \
    -e 's|smtp-server =.*|smtp-server = smtp.zoho.com|' \
    -e 's|smtp-port =.*|smtp-port = 465|' \
    -e 's|smtp-use-ssl =.*|smtp-use-ssl = 1|' \
    -e 's|smtp-user =.*|smtp-user = mpr@hunterwittenborn.com|' \
    -e "s|smtp-password =.*|smtp-password = ${mpr_smtp_password}|" \
    -e 's|sender =.*|sender = mpr@hunterwittenborn.com|' \
    -e 's|reply-to =.*|reply-to = mpr@hunterwittenborn.com|' \
    -e 's|Ed25519 =.*|Ed25519 = SHA256:TQtnFwjBwpDOHnHTaANeudpXVmomlYo6Td/8T51FA/w|' \
    -e 's|ECDSA =.*|ECDSA = SHA256:AgnXFB7JfJopUSFFJCQHvoaIQqx1RYxMLyyg2Ax7du0|' \
    -e 's|RSA =.*|RSA = SHA256:b7DzV4xdxMgUftFUFu2geQHmpe/w2c9dYEvXtJqap9Y|' \
    -e "s|ssh-cmdline =.*|ssh-cmdline = ssh mpr@${mpr_url}|" \
    -e "s|commit_hash =.*|commit_hash = ${commit_hash}|" \
    -e "s|session_secret =.*|session_secret = ${fastapi_secret}|" \
    conf/config.defaults

echo "+ Deploying..."
cd /var/www/mpr.hunterwittenborn.com
docker-compose down
find ./ -maxdepth 1 \
        -not -path './' \
        -not -path './data' \
        -exec rm -rf '{}' +

cd -
find ./ -maxdepth 1 \
        -not -path './' \
        -not -path './data' \
        -exec cp '{}' '/var/www/mpr.hunterwittenborn.com/{}' -R \;

cd /var/www/mpr.hunterwittenborn.com
docker-compose build --pull aurweb-image
docker-compose up -d nginx
