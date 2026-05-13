#!/usr/bin/env bash
# Filters the current GitLab repository against .github-private-paths and
# force-pushes the result to the GitHub staging mirror. Each step bails the
# entire job on failure so GitLab marks the job as failed (non-zero exit)
# and the github-mirror resource group is released for the next pipeline.
#
# Set MIRROR_DRY_RUN=1 to run clone + filter + leak validation only; the
# script resolves which ref *would* be pushed and skips the actual push.
# Useful for validating changes against an MR pipeline, where neither
# CI_COMMIT_BRANCH nor CI_COMMIT_TAG is set.
set -euo pipefail

: "${CI_REPOSITORY_URL:?CI_REPOSITORY_URL must be set}"
: "${STAGING_REMOTE:?STAGING_REMOTE must be set}"

WORKDIR="/tmp/filtered-repo"
PRIVATE_PATHS_RAW="/tmp/private-paths.txt"
PRIVATE_PATHS_ACTIVE="/tmp/private-paths.active"
FILTER_AUDIT_LOG="/tmp/filter-audit.log"

current_step="startup"

die() {
    echo "FATAL: $*" >&2
    exit 1
}

private_path_to_git_pathspec() {
    local private_path="$1"

    if [[ "${private_path}" == glob:* ]]; then
        printf ':(glob)%s\n' "${private_path#glob:}"
    else
        printf '%s\n' "${private_path}"
    fi
}

resolve_target_ref() {
    if [ -n "${CI_COMMIT_TAG:-}" ]; then
        target_ref_human="tag ${CI_COMMIT_TAG}"
        target_ref="refs/tags/${CI_COMMIT_TAG}"
    elif [ -n "${CI_COMMIT_BRANCH:-}" ]; then
        target_ref_human="branch ${CI_COMMIT_BRANCH}"
        target_ref="refs/heads/${CI_COMMIT_BRANCH}"
    elif [ -n "${MIRROR_DRY_RUN:-}" ] && [ -n "${CI_MERGE_REQUEST_SOURCE_BRANCH_NAME:-}" ]; then
        # MR pipelines don't set CI_COMMIT_BRANCH; for dry-runs report the MR
        # source branch so the trigger context is still visible in the log.
        target_ref_human="branch ${CI_MERGE_REQUEST_SOURCE_BRANCH_NAME} (MR ${CI_MERGE_REQUEST_IID:-?})"
        target_ref="refs/heads/${CI_MERGE_REQUEST_SOURCE_BRANCH_NAME}"
    else
        die "Neither CI_COMMIT_TAG nor CI_COMMIT_BRANCH is set; refusing to push."
    fi

    target_refspec="${target_ref}:${target_ref}"
}

step() {
    current_step="$1"
    echo
    echo "=== ${current_step} ==="
}

# Print which logical step failed; $LINENO under an ERR trap is the line where
# the failing command lives, which makes triaging long git-filter-repo runs
# much easier than scrolling the raw GitLab log.
trap 'rc=$?; echo "FATAL: github-mirror-sync failed during step \"${current_step}\" (line ${LINENO}, exit ${rc})" >&2' ERR

step "Resolve target ref"
resolve_target_ref
echo "Filtering ${target_ref_human} via ref ${target_ref}"

step "Clone current repo as bare mirror"
git clone --mirror "${CI_REPOSITORY_URL}" "${WORKDIR}"
cd "${WORKDIR}"

step "Extract denylist from .github-private-paths"
git show "${target_ref}:.github-private-paths" > "${PRIVATE_PATHS_RAW}" \
    || die ".github-private-paths is missing from ${target_ref_human}. Aborting to prevent leak."
sed 's/\r$//' "${PRIVATE_PATHS_RAW}" \
    | awk 'NF && $1 !~ /^#/ { print }' \
    > "${PRIVATE_PATHS_ACTIVE}"
if [ ! -s "${PRIVATE_PATHS_ACTIVE}" ]; then
    die ".github-private-paths has no active entries. Aborting to prevent leak."
fi

step "Paths removed from GitHub mirror"
cat "${PRIVATE_PATHS_ACTIVE}"

step "Dry-run filtered history audit"
git-filter-repo \
    --dry-run \
    --paths-from-file "${PRIVATE_PATHS_ACTIVE}" \
    --invert-paths \
    --force \
    > "${FILTER_AUDIT_LOG}" 2>&1
tail -100 "${FILTER_AUDIT_LOG}"

step "Filter history"
git-filter-repo \
    --paths-from-file "${PRIVATE_PATHS_ACTIVE}" \
    --invert-paths \
    --force

step "Post-filter leak validation"
leaked=0
while IFS= read -r path; do
    pathspec="$(private_path_to_git_pathspec "${path}")"
    if ! leaked_commit="$(git rev-list --all --max-count=1 --full-history -- "${pathspec}")"; then
        die "Leak validation failed for ${path}"
    fi
    if [ -n "${leaked_commit}" ]; then
        echo "LEAK DETECTED: ${path} still exists in filtered history"
        leaked=1
    fi
done < "${PRIVATE_PATHS_ACTIVE}"
if [ "${leaked}" -eq 1 ]; then
    die "Denylisted paths survived filtering. Aborting push."
fi

step "Configure staging remote"
git remote add staging "${STAGING_REMOTE}"
git for-each-ref --format='delete %(refname)' refs/replace | git update-ref --stdin

step "Push filtered history to staging"
if [ -n "${MIRROR_DRY_RUN:-}" ]; then
    echo "MIRROR_DRY_RUN=${MIRROR_DRY_RUN}; skipping actual push."
    echo "Would have force-pushed ${target_ref_human} via refspec ${target_refspec}"
else
    echo "Pushing filtered ${target_ref_human} to staging"
    git push staging --force "${target_refspec}"
fi

echo
echo "=== github-mirror-sync completed successfully ==="
