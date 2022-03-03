#!/bin/bash
set -eou pipefail

pip install build
python -m build
pip install dist/mprweb*.whl --force-reinstall
