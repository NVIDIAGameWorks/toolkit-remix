#!/usr/bin/env bash
# Posts RTX Remix target dependency bot results to Slack.
set -euo pipefail

: "${CI_PIPELINE_URL:?CI_PIPELINE_URL must be set}"
: "${CI_PROJECT_PATH:?CI_PROJECT_PATH must be set}"
: "${SLACK_CHANNEL_IDS_LIGHTSPEED_CI:?SLACK_CHANNEL_IDS_LIGHTSPEED_CI must be set}"
: "${SLACK_TOKEN_LIGHTSPEED_CI:?SLACK_TOKEN_LIGHTSPEED_CI must be set}"

notification_type="${1:-pipeline}"

case "${notification_type}" in
    pipeline)
        : "${CI_API_V4_URL:?CI_API_V4_URL must be set}"
        : "${CI_COMMIT_SHA:?CI_COMMIT_SHA must be set}"
        : "${CI_MERGE_REQUEST_IID:?CI_MERGE_REQUEST_IID must be set}"
        : "${CI_PIPELINE_ID:?CI_PIPELINE_ID must be set}"
        : "${CI_PROJECT_ID:?CI_PROJECT_ID must be set}"
        : "${CI_PROJECT_URL:?CI_PROJECT_URL must be set}"
        : "${REMIX_TARGET_DEP_BOT_BRANCH:?REMIX_TARGET_DEP_BOT_BRANCH must be set}"

        failed_jobs_response="$(
            curl -fsS -G \
                --data-urlencode "scope[]=failed" \
                --data-urlencode "per_page=100" \
                "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/pipelines/${CI_PIPELINE_ID}/jobs"
        )"

        if ! jq -e 'type == "array"' <<< "${failed_jobs_response}" >/dev/null; then
            echo "GitLab jobs API returned an invalid response." >&2
            exit 1
        fi

        failed_job_names="$(
            jq -r '[.[] | select(.allow_failure == false) | .name] | join(", ")' <<< "${failed_jobs_response}"
        )"

        if [ -n "${failed_job_names}" ]; then
            notification_result="failure"
            printf -v message '%s\n%s\n%s\n%s\n%s\n%s\n%s' \
                ":red_circle: *Remix dependency bot MR pipeline failed*" \
                "*Project:* \`${CI_PROJECT_PATH}\`" \
                "*Merge request:* <${CI_PROJECT_URL}/-/merge_requests/${CI_MERGE_REQUEST_IID}|!${CI_MERGE_REQUEST_IID}>" \
                "*Failed jobs:* \`${failed_job_names}\`" \
                "*Commit:* \`${CI_COMMIT_SHA}\`" \
                "*Repro:* \`git fetch origin ${REMIX_TARGET_DEP_BOT_BRANCH} && git checkout ${CI_COMMIT_SHA}\`" \
                "*Pipeline:* <${CI_PIPELINE_URL}|${CI_PIPELINE_ID}>"
        else
            notification_result="success"
            printf -v message '%s\n%s\n%s\n%s\n%s' \
                ":white_check_mark: *Remix dependency bot MR pipeline passed*" \
                "*Project:* \`${CI_PROJECT_PATH}\`" \
                "*Merge request:* <${CI_PROJECT_URL}/-/merge_requests/${CI_MERGE_REQUEST_IID}|!${CI_MERGE_REQUEST_IID}>" \
                "*Commit:* \`${CI_COMMIT_SHA}\`" \
                "*Pipeline:* <${CI_PIPELINE_URL}|${CI_PIPELINE_ID}>"
        fi
        ;;
    no-updates)
        notification_result="success"
        message=":white_check_mark: Remix dependency bot ran for ${CI_PROJECT_PATH}: no updates found. ${CI_PIPELINE_URL}"
        ;;
    scheduled-failure)
        : "${CI_COMMIT_SHA:?CI_COMMIT_SHA must be set}"
        : "${REMIX_TARGET_DEP_BOT_BRANCH:?REMIX_TARGET_DEP_BOT_BRANCH must be set}"

        notification_result="failure"
        message=":red_circle: Remix dependency bot scheduled job failed for ${CI_PROJECT_PATH}. Source SHA: ${CI_COMMIT_SHA}. Repro latest bot branch if present: git fetch origin ${REMIX_TARGET_DEP_BOT_BRANCH} && git checkout origin/${REMIX_TARGET_DEP_BOT_BRANCH}. Pipeline: ${CI_PIPELINE_URL}"
        ;;
    *)
        echo "Unknown notification type: ${notification_type}" >&2
        exit 2
        ;;
esac

channel_ids="${SLACK_CHANNEL_IDS_LIGHTSPEED_CI}"
if [ "${notification_result}" = "failure" ] && [ -n "${SLACK_FAILURE_CHANNEL_IDS_LIGHTSPEED_CI:-}" ]; then
    channel_ids="${channel_ids},${SLACK_FAILURE_CHANNEL_IDS_LIGHTSPEED_CI}"
fi

channel_ids="${channel_ids//[[:space:]]/}"
if [[ "${channel_ids}" == ,* || "${channel_ids}" == *, || "${channel_ids}" == *,,* ]]; then
    echo "Slack channel lists must not contain empty entries." >&2
    exit 1
fi

IFS=',' read -r -a slack_channel_ids <<< "${channel_ids}"
declare -A notified_channel_ids=()
notification_failed=0

for slack_channel_id in "${slack_channel_ids[@]}"; do
    if [ -n "${notified_channel_ids[${slack_channel_id}]:-}" ]; then
        continue
    fi
    notified_channel_ids["${slack_channel_id}"]=1

    if ! slack_response="$(
        curl -fsS -X POST \
            -H "Authorization: Bearer ${SLACK_TOKEN_LIGHTSPEED_CI}" \
            --data-urlencode "channel=${slack_channel_id}" \
            --data-urlencode "text=${message}" \
            https://slack.com/api/chat.postMessage
    )"; then
        echo "Slack notification request failed." >&2
        notification_failed=1
        continue
    fi

    if ! jq -e '.ok == true' <<< "${slack_response}" >/dev/null; then
        if ! slack_error="$(jq -r '.error // "unknown_error"' <<< "${slack_response}" 2>/dev/null)"; then
            slack_error="invalid_response"
        fi
        echo "Slack notification failed: ${slack_error}" >&2
        notification_failed=1
    fi
done

if [ "${notification_failed}" -ne 0 ]; then
    exit 1
fi

echo "Slack notification sent to ${#notified_channel_ids[@]} channel(s)."
