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
./docker/test-mysql-entrypoint.sh

make -C po all install
make -C test clean
make -C test sh

# Set up config file to work properly for unit tests.
sed -i 's|^user =.*|user = root|' conf/config.defaults
sed -i 's|^notify-cmd =.*|;&|' conf/config.defaults
sed -i 's|^sendmail =.*|sendmail = YOUR_AUR_ROOT/util/sendmail|' conf/config.defaults

PROMETHEUS_MULTIPROC_DIR='/tmp_prometheus' docker/scripts/run-pytests.sh --no-coverage
make -C test coverage

flake8 --count aurweb
flake8 --count test
flake8 --count migrations
isort --check-only aurweb
isort --check-only test
isort --check-only migrations
