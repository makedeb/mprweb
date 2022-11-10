#!/bin/bash
sass_watcher() {
    if [[ -z "${WATCH_SASS_FILES:+x}" ]]; then
        return 0
    fi

    sass -w -s compressed media/scss/main.scss media/css/style.css &
}

# Make sure Git is properly configured to support stored MPR package repositories owned by the 'mpr' user. Since we run as 'root' this is needed.
git config --global --add safe.directory '*'

# By default, set FASTAPI_WORKERS to 2. In production, this should
# be configured by the deployer.
if [ -z ${FASTAPI_WORKERS+x} ]; then
    FASTAPI_WORKERS=2
fi

export FASTAPI_BACKEND="$1"

echo "FASTAPI_BACKEND: $FASTAPI_BACKEND"
echo "FASTAPI_WORKERS: $FASTAPI_WORKERS"

# Perform migrations.
alembic upgrade head

# Start SCSS watcher for changes.
sass_watcher

# Actually bring up the application.
if [ "$1" == "uvicorn" ] || [ "$1" == "" ]; then
    exec uvicorn --reload \
        --log-config /docker/logging.conf \
        --host "0.0.0.0" \
        --port 8000 \
        --forwarded-allow-ips "*" \
        aurweb.asgi:app
elif [ "$1" == "gunicorn" ]; then
    exec gunicorn \
        --log-config /docker/logging.conf \
        --bind "0.0.0.0:8000" \
        --proxy-protocol \
        --forwarded-allow-ips "*" \
        -w $FASTAPI_WORKERS \
        -k uvicorn.workers.UvicornWorker \
        aurweb.asgi:app
elif [ "$1" == "hypercorn" ]; then
    exec hypercorn --reload \
        --log-config /docker/logging.conf \
        -b "0.0.0.0:8000" \
        --forwarded-allow-ips "*" \
        aurweb.asgi:app
else
    echo "Error: Invalid \$FASTAPI_BACKEND supplied."
    echo "Valid backends: 'uvicorn', 'gunicorn', 'hypercorn'."
    exit 1
fi

# vim: set ts=4 sw=4 expandtab:
