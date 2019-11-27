#!/bin/bash

set -e

source "$(dirname "${BASH_SOURCE}")/packman" --version > /dev/null
export PYTHONPATH="${PM_MODULE_DIR}:${PYTHONPATH}"
"${PM_PYTHON}" -u $@
