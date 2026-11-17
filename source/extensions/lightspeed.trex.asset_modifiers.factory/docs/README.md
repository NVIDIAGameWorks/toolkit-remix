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

An `AssetModifierBase` subclass declares `name`, `display_name`, `tooltip`, `job_type`, optional `description` and
`experimental`, and its `ModifierInput` entries. It implements `is_compatible(prim)` and `build_graph()`.
`build_graph()` adds the modifier's processing and Apply jobs after its job, reads the project stage into the job's
values, and sets the job's `skip_reason` to omit a source. The `AssetModifierJob` subclass declares its output ports
and implements `execute()`, which runs the transform.
`AssetModifierJob.get_owned_output_urls()` reports its output folder for queue cleanup.
`get_input_urls(inputs)` accepts the queue's persisted typed inputs and reports `source_url` as a required source file.

Providers call `get_instance().register_plugins([MyModifier])` at startup and `unregister_plugins()` with the same list
at shutdown.

## Provider hooks

### Modifier description

Set `description` to explain the selected modifier in the picker tooltip and its adjacent information icon.
The default is an empty string, which uses the generic picker tooltip.
Use `tooltip` for the short text on the modifier's dropdown entry.

### Conditional inputs

Set `ModifierInput.visible_if` to a predicate that returns `True` to show the row or `False` to hide it.
The default, `None`, always shows the row.
The predicate receives a mapping from input names to current values, including hidden inputs and the shared `source`
and `file` inputs. These are values converted through each input's `value_type`, not serialized settings strings.
For example, an enum input supplies an enum member, and a path input supplies a `pathlib.Path`.
An absent or invalid stored value supplies the input's `default`.

The widget evaluates predicates when it creates the rows and when settings change.
Rows follow declaration order within their groups. Declare each conditional input after the inputs that its predicate
reads, so the control appears before the row that it shows.

```python
inputs = (
    ModifierInput("show_scale", "Show Scale", bool, True),
    ModifierInput("scale", "Scale", float, 1.0, visible_if=lambda values: values["show_scale"]),
)
```

Hidden rows retain their stored values. The core still copies those values into the job.
Use `visible_if` for presentation, not to disable a parameter's effect in the transform.

### Result summary

Override `summarize_result(outputs)` to return a short message from the modifier job's durable `JobOutputs`.
The notifier calls this hook only when that job reaches `DONE`. The message appears in the completion notification
and in **Last Run**.
The default returns `None`. A `None` or empty result uses `graph name: state` instead.
Other terminal states also use that fallback. Modifier graphs use the modifier's `display_name` as their graph name.
