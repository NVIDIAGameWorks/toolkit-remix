@echo off

REM The first param is the CI_COMMIT_REF_NAME, and the second is the CI_PIPELINE_SOURCE
if /I "%~1"=="main" && /I "%~2"=="merge_request_event" (
    python tools\utils\enable_sentry.pt
)
