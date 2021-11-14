#!/usr/bin/bash
if echo "${DRONE_COMMIT_MESSAGE}" | grep -q 'TEST SKIP'; then
    echo "Skipping tests."
    exit 0
fi

set -ex

export PATH="$HOME/.poetry/bin:${PATH}"

./docker/scripts/install-deps.sh
./docker/scripts/install-python-deps.sh

useradd -U -d /aurweb -c 'AUR User' aur

./docker/mariadb-entrypoint.sh
(cd /usr && /usr/bin/mysqld_safe --datadir=/var/lib/mysql) &
until : > /dev/tcp/127.0.0.1/3306; do sleep 1s; done
./docker/test-mysql-entrypoint.sh
./docker/test-sqlite-entrypoint.sh

make -C po all install

python -m aurweb.initdb
AUR_CONFIG='conf/config.sqlite' python -m aurweb.initdb

make -C test clean
make -C test sh pytest
AUR_CONFIG='conf/config.sqlite' make -C test pytest
make -C test coverage

flake8 --count aurweb
flake8 --count test
flake8 --count migrations
isort --check-only aurweb
isort --check-only test
isort --check-only migrations
