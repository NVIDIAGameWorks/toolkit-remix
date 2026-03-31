# lightspeed.event.autosave

Periodically saves all dirty (unsaved) layers in the active RTX Remix project.

## Behaviour

- Triggers on a configurable timer after a project is opened.
- Only runs when a valid project is loaded (capture layer + replacement layer both present).
- Saves every non-anonymous dirty layer found by `LayerUtils.get_dirty_layers()`.
- Posts an in-app notification after each save cycle.
- Enabled by default at a 5-minute interval.

## Settings

All settings are persistent (survive restarts).

| Setting path | Type | Default | Description |
|---|---|---|---|
| `/persistent/exts/lightspeed.event.autosave/enabled` | bool | `true` | Master enable/disable |
| `/persistent/exts/lightspeed.event.autosave/interval_seconds` | int | `300` | Save interval in seconds |

## Preferences

Settings are exposed under **Edit > Preferences > Auto-Save**.
