#!/usr/bin/env bash

set -e

SCRIPT_DIR="$(dirname "${BASH_SOURCE}")"

# pull kit sdk
"$SCRIPT_DIR/../../../../tools/pull_kit_sdk.sh" -c release

# tests
"$SCRIPT_DIR/../../../../repo.sh" test --config release
