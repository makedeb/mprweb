#!/bin/bash
set -eou pipefail

COVERAGE=1
PARAMS=()

while [ $# -ne 0 ]; do
    key="$1"
    case "$key" in
        --no-coverage)
            COVERAGE=0
            shift
            ;;
        -*)
            echo "usage: $0 [--no-coverage] targets ..."
            exit 1
            ;;
        *)
            PARAMS+=("$key")
            shift
            ;;
    esac
done

rm -rf $PROMETHEUS_MULTIPROC_DIR
mkdir -p $PROMETHEUS_MULTIPROC_DIR

# Set up config file.
cp "${CONFIG_FILE}" conf/config
sed -i 's|^password =.*|;&|' conf/config
sed -i 's|^user =.*|user = root|' conf/config
sed -i 's|^port =.^|;&|' conf/config

cat conf/config
exit 1

# Run pytest with optional targets in front of it.
pytest -vv

# By default, report coverage and move it into cache.
if [ $COVERAGE -eq 1 ]; then
    make -C test coverage

    # /data is mounted as a volume. Copy coverage into it.
    # Users can then sanitize the coverage locally in their
    # aurweb root directory: ./util/fix-coverage ./data/.coverage
    rm -f /data/.coverage
    cp -v .coverage /data/.coverage
    chmod 666 /data/.coverage
fi
