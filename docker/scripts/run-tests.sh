#!/bin/bash
set -eou pipefail
dir=$(dirname $0)

# Run sharness tests.
#bash $dir/run-sharness.sh

# Run Python tests with MariaDB database.
# Pass --silence to avoid reporting coverage. We will do that below.
bash $dir/run-pytests.sh --no-coverage

# Run flake8 and isort checks.
for dir in aurweb test migrations; do
    black --check "${dir}/"
    flake8 --count "${dir}/"
    isort --check-only "${dir}/"
done

# vim: set sw=4 expandtab:
