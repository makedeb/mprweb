#!/usr/bin/bash
if echo "${DRONE_COMMIT_MESSAGE}" | grep -q 'TEST SKIP'; then
    echo "Skipping tests."
    exit 0
fi

# Whenever upstream changes are merged in, the 'gitlab-ci.yml' file should be checked to ensure these commands are equivilant to those there.
set -ex
AUR_CONFIG='conf/config'
DB_HOST='localhost'
TEST_RECURSION_LIMIT='10000'
CURRENT_DIR="$(pwd)"
LOG_CONFIG='logging.test.conf'
PATH="$HOME/.poetry/bin:${PATH}"
export AUR_CONFIG DB_HOST TEST_RECURSION_LIMIT CURRENT_DIR LOG_CONFIG PATH

./docker/scripts/install-deps.sh
./docker/scripts/install-python-deps.sh
useradd -U -d /aurweb -c 'AUR User' aur
./docker/mariadb-entrypoint.sh
(cd '/usr' && /usr/bin/mysqld_safe --datadir='/var/lib/mysql') &
until : > /dev/tcp/127.0.0.1/3306; do sleep 1s; done
cp -v conf/config.dev conf/config
sed -i "s;YOUR_AUR_ROOT;$(pwd);g" conf/config
./docker/test-mysql-entrypoint.sh
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
