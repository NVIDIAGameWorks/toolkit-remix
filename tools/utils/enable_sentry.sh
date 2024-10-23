#!/bin/bash
if [[ "$CI_COMMIT_REF_NAME" == "main"  && "$CI_PIPELINE_SOURCE" == "merge_request_event" ]]; then
	python tools/utils/enable_sentry.py
fi
