# lightspeed.event.autosave

Periodically saves all dirty (unsaved) layers in the active RTX Remix project.

## Behaviour

- Triggers on a configurable timer after a project is opened.
- Only runs when a valid project is loaded (capture layer + replacement layer both present).
- Disabled by default.
- When enabled, prompts before saving non-anonymous dirty layers found by `LayerUtils.get_dirty_layers()`.
- The prompt lets users save, skip the current save, or allow automatic saves for the rest of the app session.
- Posts an in-app notification after each save cycle.

## Settings

All settings are persistent (survive restarts).

| Setting path | Type | Default | Description |
|---|---|---|---|
| `/persistent/exts/lightspeed.event.autosave/enabled` | bool | `false` | Master enable/disable |
| `/persistent/exts/lightspeed.event.autosave/interval_seconds` | int | `300` | Save interval in seconds |

## Preferences

Settings are exposed under **Edit > Preferences > Auto-Save**.
