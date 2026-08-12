# omni.flux.telemetry.core

Connects Flux applications to Sentry for error and performance telemetry.

## Responsibilities

- Initialize and stop the Sentry SDK.
- Add application and session metadata.
- Report HTTP server failures. Expected HTTP 4xx validation responses are not errors.
- Remove private data from events when configured.

## Non-Responsibilities

- Define application-specific Sentry settings.
- Validate service request data.
- Handle failures in Toolkit features.

## Architecture

`TelemetryCore` resolves settings, configures Sentry integrations, and processes telemetry events. `TelemetryCoreExtension`
owns its Kit extension lifecycle.
