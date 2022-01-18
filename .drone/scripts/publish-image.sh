#!/usr/bin/bash
set -e

aurweb_config() {
    AURWEB_CONFIG='conf/config.dev' python3 -m aurweb.scripts.config "${@}"
}

# Get needed data.
commit_hash="$(git rev-parse --short HEAD)"
fastapi_secret="$(openssl rand -hex 32)"

# Set up config files.
echo "+ Setting up config files..."
cp conf/config.defaults conf/config.dev

aurweb_config set database user 'mpr'
aurweb_config set database password "${mpr_db_password}"
aurweb_config set database name 'mprweb'

aurweb_config set options aur_location "https://${mpr_url}"
aurweb_config set options git_clone_uri_anon "https://${mpr_url}/%s.git"
aurweb_config set options git_clone_uri_priv "ssh://mpr@${mpr_url}/%s.git"

aurweb_config set notifications smtp-server "${hw_url}"
aurweb_config set notifications smtp-port '465'
aurweb_config set notifications smtp-use-ssl '1'
aurweb_config set notifications smtp-user "mpr@${hw_url}"
aurweb_config set notifications smtp-password "${mpr_smtp_password}"
aurweb_config set notifications sender "mpr@${hw_url}"
aurweb_config set notifications reply-to "mpr@${hw_url}"
aurweb_config set notifications postmaster "hunter@${hw_url}"

aurweb_config set fingerprints Ed25519 'SHA256:8A1Asmd6rEtypl+h1WM/3Jgonauwx6Hez5FaytLFdwY'
aurweb_config set fingerprints ECDSA 'SHA256:7Wki/ZTENAVOYmAtH4+vhqZB8vHkLURS+eK1SQy0jTs'
aurweb_config set fingerprints RSA 'SHA256:bAWQvVgBKyuUn8acQIrEQ7Hh1PTXjghXSYovSWhrh7Y'

aurweb_config set serve ssh-cmdline "ssh mpr@${mpr_url}"
aurweb_config set devel commit_hash "$(git rev-parse --short HEAD)"
aurweb_config set fastapi session_secret "$(openssl rand -hex 32)"

echo "+ Building image..."
docker-compose build --pull --no-cache aurweb-image

echo "+ Deploying..."
cd /var/www/mpr.hunterwittenborn.com
docker-compose -f ./docker-compose.yml \
               -f ./docker-compose.mpr-override.yml \
               down --remove-orphans

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
               -f ./docker-compose.mpr-override.yml \
               up -d nginx
