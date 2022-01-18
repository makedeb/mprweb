#!/usr/bin/bash
if echo "${DRONE_COMMIT_MESSAGE}" | grep -q 'TEST SKIP'; then
    echo "Skipping tests."
    exit 0
fi

set -ex
source conf/docker.env
export PATH="$HOME/.poetry/bin:${PATH}"
export AURWEB_FASTAPI_PREFIX CONFIG_FILE

./docker/scripts/install-deps.sh
./docker/scripts/install-python-deps.sh

useradd -U -d /aurweb -c 'MPR User' mpr

./docker/mariadb-entrypoint.sh
(cd /usr && /usr/bin/mysqld_safe --datadir=/var/lib/mysql) &
until : > /dev/tcp/127.0.0.1/3306; do sleep 1s; done
cp -v conf/config.dev conf/config
sed -i "s;YOUR_AUR_ROOT;$(pwd);g" conf/config
./docker/test-mysql-entrypoint.sh

cp -vf logging.test.conf logging.conf
make -C po all install
make -C doc
make -C test clean
make -C test sh
pytest
make -C test coverage
flake8 --count aurweb
flake8 --count test
flake8 --count migrations
isort --check-only aurweb
isort --check-only test
isort --check-only migrations
