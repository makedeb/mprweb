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

mysql -u root -e "CREATE DATABASE IF NOT EXISTS ${DATABASE};"
mysql -u root -e "GRANT ALL ON ${DATABASE}.* TO '${USER}'@'%';"

mysqladmin -uroot shutdown

# Start the db.
echo "Starting db..."
/usr/bin/mysqld_safe --datadir="${MYSQL_DATA}" &
db_pid="${!}"

echo "Waiting for db to start up..."
while ! mysqladmin ping; do
	sleep 1s
done

# Initialize the db.
# Create a dummy config so we can set the host to 'localhost' for this initialization.
dummy_config="$(mktemp)"
echo -e "[database]\nhost = localhost\nname = ${DATABASE}\nuser = ${USER}\n[options]\naurwebdir=/aurweb" > "${dummy_config}"

echo "Initializing db..."
MPR_CONFIG="${dummy_config}" python -m aurweb.initdb || true
echo "${dummy_config}"

# Let the Docker Compose healthcheck know that we're done.
touch /tmp/were-done

# Return control back to the db.
echo "Returning control to db..."
wait "${db_pid}"
