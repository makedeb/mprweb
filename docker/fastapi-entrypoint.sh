#!/bin/bash
set -eou pipefail

# Setup a config for our mysql db.
cp -vf conf/config.dev conf/config
sed -i "s;YOUR_AUR_ROOT;$(pwd);g" conf/config
sed -ri "s;^(aur_location) = .+;\1 = ${AURWEB_FASTAPI_PREFIX:-'http://127.0.0.1:8080'};" conf/config

items=('DB_USER/user' 'DB_PASSWORD/password' 'DB_NAME/name' 'SMTP_SERVER/smtp-server' 'SMTP_PORT/smtp-port'
       'SMTP_USE_SSL/smtp-use-ssl' 'SMTP_USE_STARTTLS/smtp-use-starttls' 'SMTP_USER/smtp-user'
       'SMTP_PASSWORD/smtp-password' 'SMTP_SENDER/sender' 'SMTP_REPLY_TO/reply-to')

for i in "${items[@]}"; do
    IFS="/" read -r var config_item < <(echo "${i}")

    if [[ "${!var:+x}" == "x" ]]; then
        sed -i "s;^${config_item} =.*;${config_item} = ${!var};" conf/config
    fi
done

if [[ "${SESSION_SECRET:+x}" == "" ]]; then
    SESSION_SECRET="$(openssl rand -hex 20)"
fi

sed -i "s;session_secret = secret;session_secret = ${SESSION_SECRET};" conf/config

# Setup Redis for FastAPI.
sed -ri 's/^(cache) = .+/\1 = redis/' conf/config
sed -ri 's|^(redis_address) = .+|\1 = redis://redis|' conf/config

if [ ! -z ${COMMIT_HASH+x} ]; then
    sed -ri "s/^;?(commit_hash) =.*$/\1 = $COMMIT_HASH/" conf/config
fi

sed -ri "s|^(git_clone_uri_anon) = .+|\1 = ${AURWEB_FASTAPI_PREFIX}/%s.git|" conf/config.defaults
sed -ri "s|^(git_clone_uri_priv) = .+|\1 = ${AURWEB_SSHD_PREFIX}/%s.git|" conf/config.defaults

rm -rf $PROMETHEUS_MULTIPROC_DIR
mkdir -p $PROMETHEUS_MULTIPROC_DIR

exec "$@"
