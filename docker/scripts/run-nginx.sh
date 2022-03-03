#!/bin/bash

echo "=== Running nginx server! ==="
echo
echo " Services:"
echo "  - FastAPI : https://localhost:8444/"
echo
echo " Thanks for using mprweb!"
echo

exec nginx -c /etc/nginx/nginx.conf
