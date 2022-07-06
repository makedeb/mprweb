#!/bin/bash
set -eou pipefail

# Install the cron configuration.
cp /docker/config/aurweb-cron /etc/cron.d/aurweb-cron
chmod 0644 /etc/cron.d/aurweb-cron
crontab /etc/cron.d/aurweb-cron

exec "$@"
