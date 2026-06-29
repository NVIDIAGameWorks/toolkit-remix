# lightspeed.event.camera_clip_range_override

Lightspeed Event that listens for stage and Settings-prim changes and applies the project's `CameraClippingOverride` (managed by `lightspeed.trex.project_settings.core`) to every `UsdGeomCamera` prim on the active stage.

## Apply behavior

When the override is enabled, the event authors `clippingRange = (near, far)` on each camera prim using the session layer as the edit target. Session-layer authoring is the composition-strongest position in USD, so the override wins over both capture-authored and mod-layer-authored values. It is not persisted to disk; the event re-applies on every session start by reading the Settings prim.

When the override is disabled, the event restores each camera's pre-existing session-layer `clippingRange` value (if one was cached on first enable), or removes the session-layer spec entirely if no prior value existed. Either way, per-camera mod-layer authoring (or capture-authored defaults) applies normally again. The cache lives in memory only and is cleared when the stage closes.

## Event triggers

The event subscribes to:

- `StageEventType.OPENED` -> initial apply when a project loads.
- `StageEventType.HIERARCHY_CHANGED` -> re-apply when captures swap or new camera prims appear.
- `Usd.Notice.ObjectsChanged` on the Settings prim path -> re-apply immediately when the user toggles the override or edits the values.
- `StageEventType.CLOSED` -> tear down the per-stage listener and clear the restoration cache.

## Registration

This extension uses the standard `lightspeed.events_manager` pattern: the event is constructed in `on_startup` and registered with the events manager. The USD context name is read from the carb setting `/exts/lightspeed.event.camera_clip_range_override/context` (defaults to the empty string, i.e., the default USD context).
