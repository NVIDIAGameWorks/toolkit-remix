# lightspeed.trex.asset_modifiers.core

Run local model transforms through the Job Queue. A modifier accepts any prim type that
its `is_compatible()` accepts, for example meshes, materials, or shaders, when an external model reference composes it.

## Responsibilities

- Store the active modifier, its source, and its typed input values.
- Resolve the source models of the active modifier and build one job per source model.
- Leave out the jobs that a modifier skips, and report why.

## Non-Responsibilities

- `lightspeed.trex.asset_modifiers.factory` registers the modifiers and defines the provider API.
- The widget extension owns the window. Provider extensions own their transforms.
- Each modifier builds its own graph: which processing jobs follow its job, and which Apply handler applies it.
- The asset pipeline owns the processing jobs and `AssetReplaceApplyHandler`, which ComfyUI also uses.

## Architecture

`AssetModifierSettings` stores the active modifier name and the input values, and notifies the factory's
`subscribe_changed()` subscribers. `constants.py` declares the Source inputs that every modifier shows before its own
inputs.

`AssetModifiersCore(context_name)` holds no state of its own. It resolves the active modifier from the factory, returns
the Stage Manager and Run block reasons, and prepares the graphs for its USD context.

`prepare_submission()` builds the job of each source model and a graph named after the modifier that holds it. It
passes both to the modifier's `build_graph()` with the source references as an `AssetReplaceApplyTarget`, and returns
the graphs and the reason for each skipped prim path.
File Path Constant sources have no target. Saved
projects publish to `assets/ingested/modifiers/<name>/<job id>/`, so runs never overwrite each other, as in AI Tools.

## Add a modifier

The test modifier in [scale_mesh_modifier.py](../lightspeed/trex/asset_modifiers/core/tests/e2e/scale_mesh_modifier.py)
and its job in [scale_mesh_job.py](../lightspeed/trex/asset_modifiers/core/tests/e2e/scale_mesh_job.py) are an example.
They use the provider API from `lightspeed.trex.asset_modifiers.factory`.

1. Derive a job from `AssetModifierJob`, declare its output ports, and implement `execute()`. This is the transform.
   A model for mesh optimization uses absolute texture and sub-USD paths and plain image textures.
2. Derive a modifier from `AssetModifierBase`. Declare `name`, `display_name`, `tooltip`, `job_type`, optional
   `experimental`, and `ModifierInput` entries, and implement `is_compatible(prim)`.
3. Implement `build_graph(stage, graph, job, target)`. Add the jobs that process the job's output, for example
   `add_asset_optimization_jobs()`, with the Apply handler that fits the modifier, for example
   `AssetReplaceApplyHandler` with `target`. Read the project stage into `job.values` here, and set
   `job.skip_reason` to leave that source out while the other sources continue.
4. Call `get_instance().register_plugins([MyModifier])` from the factory extension at provider startup and
   `unregister_plugins()` with the same list at shutdown.
