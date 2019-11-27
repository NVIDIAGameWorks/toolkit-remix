#!/bin/bash

set -e

./build.sh --rebuild $* || exit 1

