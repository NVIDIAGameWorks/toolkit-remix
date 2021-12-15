#!/usr/bin/env bash

set -e

SCRIPT_DIR="$(dirname "${BASH_SOURCE}")"

# Build release
"$SCRIPT_DIR/../../../../build.sh"

# Package
"$SCRIPT_DIR/../../../../repo.sh" package -m main_package -c release

"$SCRIPT_DIR/../../../../repo.sh" package -m main_package -c debug

# publish artifacts to teamcity
echo "##teamcity[publishArtifacts '_build/packages/*']"


