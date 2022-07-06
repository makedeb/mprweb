#!/usr/bin/env bash
set -eou pipefail

echo '== If the database has already been initialized, this may show an error! =='
python -m aurweb.initdb || /bin/true
