#!/usr/bin/bash
if echo "${DRONE_COMMIT_MESSAGE}" | grep -q 'TEST SKIP'; then
    echo "Skipping tests."
    exit 0
fi

set -ex
AUR_CONFIG="${PWD}/conf/config"
DB_HOST='localhost'
TEST_RECURSION_LIMIT='10000'
CURRENT_DIR="$(pwd)"
LOG_CONFIG='logging.test.conf'
PYTHONPATH="${PWD}:${PWD}/app"
export AUR_CONFIG DB_HOST TEST_RECURSION_LIMIT CURRENT_DIR LOG_CONFIG PYTHONPATH

./docker/scripts/install-deps.sh
./docker/scripts/install-python-deps.sh
useradd -U -d /aurweb -c 'AUR User' mpr
./docker/mariadb-entrypoint.sh
(cd '/usr' && /usr/bin/mysqld_safe --datadir='/var/lib/mysql') &
until : > /dev/tcp/127.0.0.1/3306; do sleep 1s; done
cp -v conf/config.dev conf/config
sed -i "s;YOUR_AUR_ROOT;$(pwd);g" conf/config
./docker/test-mysql-entrypoint.sh
make -C po all install
make -C doc
pytest
black ./
flake8 --count ./
isort --check-only ./
