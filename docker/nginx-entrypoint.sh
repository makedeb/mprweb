#!/bin/bash
set -eou pipefail

cp -vf /docker/config/nginx.conf /etc/nginx/nginx.conf

exec "$@"
