#!/bin/bash
if [[ "$CI_COMMIT_REF_NAME" == "main"  && "$CI_PIPELINE_SOURCE" == "push" ]]; then
	python tools/utils/enable_sentry.py
fi
