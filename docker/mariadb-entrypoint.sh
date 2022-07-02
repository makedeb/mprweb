#!/bin/bash
set -eou pipefail

MYSQL_DATA=/var/lib/mysql

mariadb-install-db --user=mysql --basedir=/usr --datadir="${MYSQL_DATA}"

# Start it up.
mysqld_safe --datadir=$MYSQL_DATA --skip-networking &
while ! mysqladmin ping --silent; do
    sleep 1s
done

# Configure databases.
DATABASE="$(aurweb-config get database name)" # Persistent database for FastAPI.
USER="$(aurweb-config get database user)"
PASSWORD="$(aurweb-config get database password)"

echo "Taking care of primary database '${DATABASE}'..."
mysql -u root -e "CREATE USER IF NOT EXISTS '${USER}'@'%' IDENTIFIED BY '${PASSWORD}';"
mysql -u root -e "CREATE USER IF NOT EXISTS '${USER}'@'localhost' IDENTIFIED BY '${PASSWORD}';"

mysql -u root -e "CREATE DATABASE IF NOT EXISTS ${DATABASE};"
mysql -u root -e "GRANT ALL ON ${DATABASE}.* TO '${USER}'@'%';"
mysql -u root -e "GRANT ALL ON ${DATABASE}.* TO '${USER}'@'localhost';"

mysqladmin -uroot shutdown

# Start mysql back up with networking.
/usr/bin/mysqld_safe --datadir=/var/lib/mysql
