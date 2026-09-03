#!/usr/bin/env bash
# Posts the "source changed without test changes" report as a merge request note.
#
# The note is idempotent: it carries a hidden marker so repeated pipeline runs update the existing note instead of
# adding a new one, and the note is rewritten as resolved once the tests show up.
set -euo pipefail

REPORT_FILE="${1:-missing-tests.md}"
NOTE_MARKER="<!-- check-tests-written -->"

# A missing token must not fail the pipeline. The job already reports the warning through its own exit code, so the
# comment is a convenience on top of it.
if [ -z "${TOOLKIT_GITLAB_MR_NOTE_TOKEN:-}" ]; then
    echo "TOOLKIT_GITLAB_MR_NOTE_TOKEN is not set. Skipping the merge request comment."
    exit 0
fi

: "${CI_API_V4_URL:?CI_API_V4_URL must be set}"
: "${CI_MERGE_REQUEST_IID:?CI_MERGE_REQUEST_IID must be set}"
: "${CI_PROJECT_ID:?CI_PROJECT_ID must be set}"

notes_url="${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/merge_requests/${CI_MERGE_REQUEST_IID}/notes"

find_existing_note_id() {
    local page=1
    local response
    local note_id

    # The notes endpoint pages at 100 entries; walk the pages until the marker is found or the list runs out.
    while [ "${page}" -le 20 ]; do
        if ! response="$(
            curl -fsS -G \
                -H "PRIVATE-TOKEN: ${TOOLKIT_GITLAB_MR_NOTE_TOKEN}" \
                --data-urlencode "per_page=100" \
                --data-urlencode "page=${page}" \
                "${notes_url}"
        )"; then
            echo "Failed to list merge request notes." >&2
            return 1
        fi

        if ! jq -e 'type == "array"' <<< "${response}" >/dev/null; then
            echo "GitLab notes API returned an invalid response." >&2
            return 1
        fi

        if [ "$(jq -r 'length' <<< "${response}")" -eq 0 ]; then
            break
        fi

        note_id="$(jq -r --arg marker "${NOTE_MARKER}" \
            'map(select(.body | contains($marker))) | first | .id // empty' <<< "${response}")"
        if [ -n "${note_id}" ]; then
            printf '%s' "${note_id}"
            return 0
        fi

        page=$((page + 1))
    done

    return 0
}

if [ -f "${REPORT_FILE}" ]; then
    body="${NOTE_MARKER}"$'\n'"$(cat "${REPORT_FILE}")"
else
    body="${NOTE_MARKER}"$'\n'":white_check_mark: **Test check passed** — every extension with changed Python source also has changed test files."
fi

existing_note_id="$(find_existing_note_id)"

if [ -z "${existing_note_id}" ]; then
    # Nothing to report and no stale note to clear: stay silent rather than commenting on every passing merge request.
    if [ ! -f "${REPORT_FILE}" ]; then
        echo "No findings and no existing note. Nothing to comment."
        exit 0
    fi

    if ! curl -fsS -X POST \
        -H "PRIVATE-TOKEN: ${TOOLKIT_GITLAB_MR_NOTE_TOKEN}" \
        --data-urlencode "body=${body}" \
        "${notes_url}" >/dev/null; then
        echo "Failed to create the merge request note." >&2
        exit 1
    fi

    echo "Created merge request note."
    exit 0
fi

if ! curl -fsS -X PUT \
    -H "PRIVATE-TOKEN: ${TOOLKIT_GITLAB_MR_NOTE_TOKEN}" \
    --data-urlencode "body=${body}" \
    "${notes_url}/${existing_note_id}" >/dev/null; then
    echo "Failed to update the merge request note." >&2
    exit 1
fi

echo "Updated merge request note ${existing_note_id}."
