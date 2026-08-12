# omni.flux.telemetry.core

Connects Flux applications to Sentry for error and performance telemetry.

## Responsibilities

- Initialize and stop the Sentry SDK.
- Add application and session metadata.
- Report HTTP server failures. Expected HTTP 4xx validation responses are not errors.
- Remove private data from events when configured.
- Apply optional application-configured event filtering.

## Non-Responsibilities

- Define application-specific Sentry settings.
- Validate service request data.
- Handle failures in Toolkit features.

## Architecture

`TelemetryCore` resolves settings, configures Sentry integrations, and processes telemetry events. `TelemetryCoreExtension`
owns its Kit extension lifecycle.

The optional `sentry_event_filter` settings define application-owned module roots, external exception module roots,
and whether events without usable origin metadata are dropped. The generic extension disables this policy by default.

Transactions are always kept. For exceptions, the newest frame of each exception value defines its origin, while a
configured external exception module overrides the frame for that value. Any independently owned exception value keeps
the full event. Messages with an external logger are filtered. Messages without a logger follow
`drop_unattributed_events`. The policy does not use `handled`, Sentry `in_app` values, event text, file paths, or issue
IDs.

Module roots use exact dotted boundaries. Empty owned roots disable filtering.
