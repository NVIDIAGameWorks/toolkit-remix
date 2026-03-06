# Implementing Ingestion Pipeline Plugins

The Validation Pipeline (Flux) / Ingestion Pipeline (Remix) is a schema-driven validation framework with 4 plugin types.
It powers asset ingestion in IngestCraft (`"ingestcraft"` USD context) and can be reused for any validation workflow.

The Flux layer (`omni.flux.validator.*`) provides the generic framework. The Lightspeed layer uses it for model and
material ingestion with Remix-specific checks and fixes.

---

## Plugin Types

All plugins inherit from a common base (`Base`) that provides progress tracking, event subscriptions, data flow
channels, and optional UI building. Plugins are executed in a defined order by the `ManagerCore`.

| Plugin type        | Base class     | Key methods                       | Role                                                                                                                                                                                                                              |
|--------------------|----------------|-----------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **ContextPlugin**  | `ContextBase`  | `check()`, `setup()`, `on_exit()` | Sets up environment (opens USD stage, configures I/O paths). `check()` validates preconditions, `setup()` prepares the context and triggers the check pipeline via `run_callback`, `on_exit()` cleans up (e.g., saves the stage). |
| **SelectorPlugin** | `SelectorBase` | `select()`                        | Selects data from the context (all prims, all meshes, all materials). Chains with other selectors — each receives the previous selector's output.                                                                                 |
| **CheckPlugin**    | `CheckBase`    | `check()`, `fix()`                | Validates selected items and optionally auto-fixes failures. Has `stop_if_fix_failed` and `pause_if_fix_failed` control flags. Each check has its own selector chain and optional per-check context.                              |
| **ResultorPlugin** | `ResultorBase` | `result()`                        | Post-processing after all checks complete (file cleanup, metadata writing). Operates on the entire schema's accumulated data.                                                                                                     |

All methods are async and return `(bool, str, ...)` tuples — success flag plus a human-readable message.

---

## Execution Flow

```text
Context.check()          → validate preconditions (e.g., USD file exists)
Context.setup()          → prepare environment, then run pipeline:
  │
  ├─ For each CheckPlugin:
  │   ├─ Run SelectorPlugins (chain)  → filter data
  │   ├─ Check.check()                → validate
  │   └─ If failed:
  │       ├─ Re-run SelectorPlugins
  │       └─ Check.fix()              → auto-fix
  │           ├─ stop_if_fix_failed   → halt pipeline
  │           └─ pause_if_fix_failed  → pause for review
  │
  ├─ Run ResultorPlugins              → post-processing
  │
Context.on_exit()        → cleanup (save stage, close files)
```

Progress is tracked continuously: context takes 0–50%, check groups take 50–100% distributed across checks and
resultors.

---

## Schema Structure

The full pipeline is defined by a JSON schema. The `ManagerCore` loads and resolves it into `ValidationSchema` models at
startup.

```json
{
  "context_plugin": {
    "name": "AssetImporter",
    "data_flows": [{"name": "InOutData", "input_data": ["..."], "output_data": ["..."]}]
  },
  "check_plugins": [
    {
      "name": "DefaultMaterial",
      "selector_plugins": [{"name": "AllMeshes", "data": {}}],
      "context_plugin": null,
      "resultor_plugins": null,
      "stop_if_fix_failed": false,
      "pause_if_fix_failed": false
    },
    {
      "name": "ConvertToDDS",
      "selector_plugins": [{"name": "AllShaders", "data": {}}],
      "data_flows": [
        {"name": "InOutData", "channel": "cleanup_files", "push_output_data": true},
        {"name": "InOutData", "channel": "write_metadata", "push_output_data": true}
      ]
    }
  ],
  "resultor_plugins": [
    {"name": "FileCleanup", "channel": "cleanup_files"},
    {"name": "FileMetadataWritter", "channel": "write_metadata"}
  ]
}
```

Real schemas live at:

- `source/extensions/lightspeed.trex.app.resources/data/validation_schema/model_ingestion.json`
- `source/extensions/lightspeed.trex.app.resources/data/validation_schema/material_ingestion.json`

---

## DataFlow System

Plugins pass data between each other via named channels using `InOutDataFlow`:

```python
class InOutDataFlow(DataFlow):
    name: str = "InOutData"
    input_data: list[str] | None = None
    push_input_data: bool = False
    output_data: list[str] | None = None
    push_output_data: bool = False
    channel: str | None = "Default"
```

A check plugin can push output to a named channel (e.g., `"cleanup_files"`), and a resultor plugin listening on that
channel receives the accumulated data. This decouples checks from post-processing — multiple checks can push to the same
channel.

---

## Mass Validation

`MassValidator` enables batch operations — processing multiple assets through the same validation pipeline:

- **Template cooking**: A single pipeline schema is used as a template. Plugins with `cook_mass_template=True` generate
  N concrete schemas (one per asset) from user input.
- **Queue UI**: Assets are queued with progress tracking per item.
- **Progress tracking**: Each schema's `send_request=True` flag triggers HTTP callbacks to the mass validator for
  real-time status updates.

---

## Run Modes

The manager supports three run modes for re-running parts of the pipeline:

| Mode                 | Behavior                                           |
|----------------------|----------------------------------------------------|
| `BASE_ALL`           | Re-run all plugins from the beginning              |
| `BASE_ONLY_SELECTED` | Run only specific plugins + their context          |
| `BASE_SELF_TO_END`   | Run from a specific plugin to the end of the chain |

---

## Extension Reference

### Core Framework

| Extension                          | Role                                                        |
|------------------------------------|-------------------------------------------------------------|
| `omni.flux.validator.factory`      | Plugin base classes, factory registration, data flow system |
| `omni.flux.validator.manager.core` | `ManagerCore` — orchestrates the full validation pipeline   |
| `omni.flux.validator.mass.core`    | `MassValidator` — batch processing with template cooking    |

### Generic Plugins

| Extension                                      | Role                                                                     |
|------------------------------------------------|--------------------------------------------------------------------------|
| `omni.flux.validator.plugin.context.usd_stage` | Opens/saves USD stages as validation context                             |
| `omni.flux.validator.plugin.selector.usd`      | USD selectors (AllPrims, AllMeshes, AllMaterials, AllShaders, RootPrims) |
| `omni.flux.validator.plugin.check.usd`         | USD validation checks (materials, shaders, references, unit scale)       |
| `omni.flux.validator.plugin.resultor.file`     | File operations (cleanup, metadata writing)                              |

### UI

| Extension                            | Role                                                                 |
|--------------------------------------|----------------------------------------------------------------------|
| `omni.flux.validator.manager.widget` | Validation manager UI — displays check status, progress, fix buttons |
| `omni.flux.validator.mass.widget`    | Mass validation queue UI — batch progress tracking                   |

### Ingestion (Remix)

| Extension                                      | Role                                               |
|------------------------------------------------|----------------------------------------------------|
| `lightspeed.trex.ingestcraft.widget`           | IngestCraft layout widget — hosts the ingestion UI |
| `lightspeed.trex.layout.shared.mass_ingestion` | Mass ingestion layout — batch asset processing     |

See each extension's `docs/README.md` for implementation details.
