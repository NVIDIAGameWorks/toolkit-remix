# lightspeed.trex.app.setup

Finalizes the RTX Remix application UI after Kit startup and exposes the application-owned user-readiness lifecycle.

## Responsibilities

- Apply the production menu layout and Windows titlebar styling.
- Close the Kit splash screen after the selected application layout is ready.
- Publish `USER_READY` once after the StageCraft Home window reports `HOME_INTERACTIVE` and a final UI update runs.
- Preserve the fixed-frame setup fallback for application layouts that do not use Home.

## Non-Responsibilities

- Does not create, dock, or populate the Home workspace; `lightspeed.trex.home.widget` owns that UI.
- Does not include recent-project cards in the `USER_READY` contract; Home reports those separately.
- Does not replace Kit's `EVENT_APP_READY`, which remains the signal that Kit startup itself completed.

## Architecture

`SetupUI` subscribes to Kit app-ready, owns the deferred setup task, and applies the menu, splash, and titlebar changes.
For the StageCraft layout it waits up to 30 seconds for Home's supported lifecycle signal, closes the splash, yields one
UI update, and publishes `USER_READY`. Timeout and failure paths close the splash without claiming user readiness.

`lifecycle.py` owns the process-local readiness state. Home publishes through the public `mark_home_interactive()` API,
and `subscribe_user_ready()` supports both early and late subscribers while ignoring duplicate publications.
`MenubarIgnore` translates the configured menu filter into Kit menu layouts.
