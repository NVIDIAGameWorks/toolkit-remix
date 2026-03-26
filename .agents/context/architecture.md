## Code Architecture

Read `docs_dev/architecture/overview.md` for the complete architecture reference. The directives below are what you must
apply to every decision — they produce broken or wrong code if ignored.

### Extension Naming — determines every file name and dependency structure

Choose suffix based on role: `.core` (logic, no UI), `.widget` (on Frame/Stack only), `.window` (wraps widgets),
`.menu` (menu items), `.controller` (entry point, wires everything), `.model` (tree/list data), `.service` (REST),
`.plugin.*` (factory plugin), `.style` (global stylesheet), `.bundle` (meta-ext).

Dependency direction: `.controller` → `.widget` + `.core`. `.widget` and `.core` must **never** depend on each other.

Generic code → `omni.flux.*`. RTX Remix-specific behavior → `lightspeed.trex.*`.

### Extension Dependencies — `extension.toml` must match actual imports

`[dependencies]` in `config/extension.toml` must exactly match the extension's actual imports — add missing, prune
unused. Add `"omni.flux.pip_archive" = {}` if the extension imports any third-party pip package.

### USD Contexts — wrong context = silent failures across layouts

| String value     | Layout                      |
|------------------|-----------------------------|
| `""` (default)   | Modding Layout (StageCraft) |
| `"ingestcraft"`  | Ingestion Layout            |
| `"texturecraft"` | AI Tools Layout             |

**Always pass `context_name` explicitly. Never assume the default.**

### Extension Lifecycle — determines `on_startup`/`on_shutdown` structure

- Single instance → module-level `_INSTANCE` + `get_instance()`
- Stage-aware → `_instances: dict[str, T]` keyed by `context_name`, `get_instance(context_name: str = "")`
- Multiple attrs to tear down → `default_attr` dict + `reset_default_attrs(self)` from `omni.flux.utils.common`
- Pure library (no lifecycle) → omit `extension.py`, register via `[[python.module]]` only

### Event Subscriptions — subscriptions garbage-collected if not stored

`EventSubscription` is only active while referenced. **Always assign to `self`** — not a local variable.

Use `lightspeed.events_manager` for cross-extension Remix lifecycle events. Use `omni.flux.utils.common.Event` for
single-extension public API events.

### Widget Rule

Always build on `omni.ui.Frame` or `omni.ui.Stack`. Never `omni.ui.Window`. Never inline stylesheets — styles belong in
the app-level `.style` extension.

### Commands Rule

All user-facing data mutations require `omni.kit.commands.Command` with `do()` + `undo()`. Direct mutations are rejected
in review.

Full architecture reference: `docs_dev/architecture/overview.md`. Extension naming and structure:
`docs_dev/architecture/extension-guide.md`.
