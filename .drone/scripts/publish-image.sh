#!/usr/bin/bash
set -ex

aurweb_config() {
    MPR_CONFIG='./mprweb.cfg' python3 -m aurweb.scripts.config "${@}"
}

# Temporary variables until the Drone Exec runner supports variables from environment extensions.
export makedeb_url='makedeb.org'
export mpr_url='mpr.makedeb.org'
export hw_url='hunterwittenborn.com'

# Get needed data.
commit_hash="$(git rev-parse --short HEAD)"

# Set up config files.
echo "+ Setting up config files..."

aurweb_config set database user 'mpr'
aurweb_config set database password "${mpr_db_password}"
aurweb_config set database name 'mprweb'

aurweb_config set options aur_location "https://${mpr_url}"
aurweb_config set options git_clone_uri_anon "https://${mpr_url}/%s.git"
aurweb_config set options git_clone_uri_priv "ssh://mpr@${mpr_url}/%s.git"
aurweb_config set options traceback 0

aurweb_config set sentry dsn "${mpr_sentry_dsn}"
aurweb_config set sentry traces_sample_rate '1.0'

aurweb_config set notifications smtp-server 'smtp.gmail.com'
aurweb_config set notifications smtp-port '465'
aurweb_config set notifications smtp-use-ssl '1'
aurweb_config set notifications smtp-user "kavplex@${hw_url}"
aurweb_config set notifications smtp-password "${mpr_smtp_password}"
aurweb_config set notifications sender "MPR <mpr@${makedeb_url}>"
aurweb_config set notifications reply-to "mpr@${makedeb_url}"

ed25519_key="$(ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub  | awk '{print $2}')"
ecdsa_key="$(ssh-keygen -lf /etc/ssh/ssh_host_ecdsa_key.pub  | awk '{print $2}')"
rsa_key="$(ssh-keygen -lf /etc/ssh/ssh_host_rsa_key.pub  | awk '{print $2}')"

aurweb_config set fingerprints Ed25519 "${ed25519_key}"
aurweb_config set fingerprints ECDSA "${ecdsa_key}"
aurweb_config set fingerprints RSA "${rsa_key}"

aurweb_config set devel commit_hash "$(git rev-parse --short HEAD)"

aurweb_config set fastapi session_secret "${mpr_fastapi_session_secret}"

echo "+ Building image..."
docker-compose build --pull --no-cache aurweb-image

echo "+ Deploying..."
cd /var/www/mpr.makedeb.org
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
        -exec cp '{}' '/var/www/mpr.makedeb.org/{}' -R \;

cd /var/www/mpr.makedeb.org
docker-compose -f ./docker-compose.yml \
               -f ./docker-compose.mpr-override.yml \
               up -d nginx
