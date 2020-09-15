#!/bin/bash
set -e

if [ -z $1 ]
then
    platform=linux-x86_64
else
    platform=$1
fi

SCRIPT_DIR=$(dirname ${BASH_SOURCE})

pushd "$SCRIPT_DIR/.."

if [ -d _build/PACKAGE-LICENSES ]
then
    rm _build/PACKAGE-LICENSES/* || true
fi

"tools/licensing.sh" gather -d "." -p "deps/target-deps.packman.xml" --platform "linux-x86_64" $LICENSING_OPTIONS $@
