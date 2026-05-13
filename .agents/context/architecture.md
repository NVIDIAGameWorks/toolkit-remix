## Architecture Rules

Full refs: `docs_dev/architecture/overview.md`, `docs_dev/architecture/extension-guide.md`.

- Suffix = role: `.core` logic/no UI; `.widget` UI on Frame/Stack; `.window` wraps widgets; `.menu` menu items;
  `.model` tree/list data; `.service` REST; `.plugin.*` factory plugin; `.style` stylesheet; `.bundle` meta-ext.
- Feature entry ext wires `.core`, `.widget`/`.window`, `.menu`; match nearby naming/loading.
- Dependency direction: entry -> `.widget` + `.core`. `.widget` <-> `.core` forbidden.
- Generic -> `omni.flux.*`. Remix-specific -> `lightspeed.trex.*`.
- `config/extension.toml` deps must match imports. Add `omni.flux.pip_archive` for third-party pip imports.
- USD contexts: `""` StageCraft, `"ingestcraft"` ingestion, `"texturecraft"` AI Tools. Always pass `context_name`;
  default causes silent wrong-layout failures.
- Lifecycle: single instance -> module `_INSTANCE` + `get_instance()`. Stage-aware -> `_instances[context_name]`.
  Multiple teardown attrs -> explicit cleanup in `on_shutdown` / `destroy`; do not add new `default_attr` /
  `reset_default_attrs` usage. Pure library -> no `extension.py`, only `[[python.module]]`.
- Store event subscriptions on `self`; locals get garbage-collected. Cross-extension Remix events ->
  `lightspeed.events_manager`; single-extension public API -> `omni.flux.utils.common.Event`.
- Reusable `.widget` UI: build on `omni.ui.Frame` / `omni.ui.Stack`, not `omni.ui.Window`; `.window` / feature entry
  extensions may own actual windows. No inline stylesheets; use app `.style`.
- User-facing data mutation -> `omni.kit.commands.Command` with `do()` + `undo()`. Direct mutation rejected.
