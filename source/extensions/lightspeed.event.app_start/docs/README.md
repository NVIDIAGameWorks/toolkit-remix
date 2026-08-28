# lightspeed.event.app_start

Records startup telemetry without putting device discovery on the user-facing startup path.

## Responsibilities

- Capture the app launch and Kit-ready timestamps.
- Wait for the supported `USER_READY` lifecycle event and one additional update before querying device and memory
  information.
- Preserve the existing App Startup transaction semantics while recording the user-ready duration separately.

## Non-responsibilities

- Publishing application lifecycle milestones.
- Determining when the Home page or another workspace is usable.
- Initializing or configuring the telemetry service.

## Architecture

`EventAppStartCore` subscribes to Kit app-ready once. It captures the Kit-ready timestamp, subscribes to
`lightspeed.trex.app.setup.lifecycle.USER_READY`, and owns the short asynchronous task that records telemetry on the
following update. Uninstalling releases both subscriptions and cancels pending collection.
