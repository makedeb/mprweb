#!/bin/bash
set -eou pipefail

# Setup prometheus directory.
rm -rf $PROMETHEUS_MULTIPROC_DIR
mkdir -p $PROMETHEUS_MULTIPROC_DIR

exec "$@"
