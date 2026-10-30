# lightspeed.trex.asset_modifiers.factory

Register asset modifier plugins. Provider extensions register their `AssetModifierBase` subclasses here, and the
Asset Modifiers core and window read them back.

## Responsibilities

- Own the process-wide `AssetModifierFactory`, returned by `get_instance()`.
- Define the provider API: `AssetModifierBase`, `AssetModifierJob`, and `ModifierInput`.
- Register the codecs that persist each modifier's jobs and enum inputs.
- Notify subscribers when modifiers register or unregister, or when their settings change.

## Non-Responsibilities

- `lightspeed.trex.asset_modifiers.core` stores the settings and prepares the Job Queue graphs.
- `lightspeed.trex.asset_modifiers.widget` owns the window.
- Provider extensions own their transforms.

## Architecture

`AssetModifiersFactoryExtension` creates one `AssetModifierFactory`, a Flux `FactoryBase` keyed by each plugin's
`name`. `register_plugins()` also registers an `asset_modifiers.<name>` codec for the plugin's `job_type`, plus one
codec per enum input. Codecs stay registered after `unregister_plugins()` so queued jobs can still restore. Keep the
object from `subscribe_changed()` to follow registration and settings changes.

An `AssetModifierBase` subclass declares `name`, `display_name`, `tooltip`, `job_type`, optional `experimental`, and
its `ModifierInput` entries, and implements `is_compatible(prim)` and `build_graph()`. `build_graph()` adds the
modifier's processing and Apply jobs after its job, reads the project stage into the job's values, and sets the job's
`skip_reason` to leave a source out. The `AssetModifierJob` subclass is a plain Job Queue job: it declares its output
ports and implements `execute()`, which is the transform.

Providers call `get_instance().register_plugins([MyModifier])` at startup and `unregister_plugins()` with the same list
at shutdown.
