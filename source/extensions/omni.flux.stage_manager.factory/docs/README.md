# omni.flux.stage_manager.factory

Plugin registration and reusable plugin, tree, and row-action contracts for Stage Manager.

## Responsibilities

- Register Stage Manager plugins and their context menus.
- Define base contracts for contexts, interactions, filters, trees, columns, widgets, and listeners.
- Resolve generic row-action targets from the published model and its selection.

## Non-Responsibilities

- Resolving schemas and orchestrating active interactions belong to `omni.flux.stage_manager.core`.
- USD prim validation and concrete actions belong to the USD widget plugin extensions.

## Architecture

- `StageManagerFactory` registers plugin classes and coordinates menu registration.
- `StageManagerTreeModel` manages canonical items and published proxies; `StageManagerTreeDelegate` handles row events.
- `StageManagerWidgetPlugin` supplies the overridable `_get_action_items(model, item)` helper and `_action_row_only`
  policy. See [row action targets](../../../../docs_dev/patterns/stage-manager.md#row-action-targets).
