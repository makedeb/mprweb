#!/bin/bash
set -eou pipefail
dir=$(dirname $0)

# Run Python tests with MariaDB database.
# Pass --silence to avoid reporting coverage. We will do that below.
bash $dir/run-pytests.sh --no-coverage

# Run black, flake8, and isort checks.
black --check ./
flake8 --count ./
isort --check-only ./

# vim: set sw=4 expandtab:
