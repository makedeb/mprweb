#!/bin/bash

COVERAGE=1
PARAMS=()

while [ $# -ne 0 ]; do
    key="$1"
    case "$key" in
        --no-coverage)
            COVERAGE=0
            shift
            ;;
        clean)
            rm -f .coverage
            shift
            ;;
        *)
            echo "usage: $0 [--no-coverage] targets ..."
            exit 1
            ;;
    esac
done

rm -rf $PROMETHEUS_MULTIPROC_DIR
mkdir -p $PROMETHEUS_MULTIPROC_DIR

# Run pytest with optional targets in front of it.
pytest
