#!/usr/bin/env bash
# Verifies that git-filter-repo is installed on the GitLab runner before the
# github-mirror-sync job uses it. Fails with an actionable message pointing at
# the AWX template that provisions the dependency.
set -euo pipefail

if ! command -v git-filter-repo >/dev/null 2>&1; then
    echo "FATAL: git-filter-repo is missing on this runner." >&2
    exit 1
fi

git-filter-repo --version
