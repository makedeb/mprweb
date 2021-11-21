#!/bin/bash
set -eou pipefail

MYSQL_DATA=/var/lib/mysql
DB_USER="${DB_USER:-mpr}"
DB_PASSWORD="${DB_PASSWORD:-mpr}"

mariadb-install-db --user=mysql --basedir=/usr --datadir=$MYSQL_DATA

# Start it up.
mysqld_safe --datadir=$MYSQL_DATA --skip-networking &
while ! mysqladmin ping 2>/dev/null; do
    sleep 1s
done

# Configure databases.
DATABASE="mprweb" # Persistent database for fastapi/php-fpm.

echo "Taking care of primary database '${DATABASE}'..."
mysql -u root -e "CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';"
mysql -u root -e "CREATE USER IF NOT EXISTS '${DB_USER}'@'%' IDENTIFIED BY '${DB_PASSWORD}';"
mysql -u root -e "CREATE DATABASE IF NOT EXISTS $DATABASE;"
mysql -u root -e "GRANT ALL ON ${DATABASE}.* TO '${DB_USER}'@'localhost';"
mysql -u root -e "GRANT ALL ON ${DATABASE}.* TO '${DB_USER}'@'%';"

mysqladmin -uroot shutdown

exec "$@"
