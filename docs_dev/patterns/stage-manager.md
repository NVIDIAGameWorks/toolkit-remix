# Implementing Stage Manager Plugins

The Stage Manager is a tabbed, plugin-driven tree/table UI for browsing USD stages. It powers the main asset panel in
the Modding Layout and is the most complex UI framework in the codebase.

The Flux layer (`omni.flux.stage_manager.*`) provides the generic, reusable core. The Lightspeed layer (
`lightspeed.trex.stage_manager.*`) adds Remix-specific behavior on top.

---

## Plugin Types

All plugins inherit from `StageManagerPluginBase` (Pydantic `BaseModel` + ABC). The `name` class variable is
automatically set to the class name and is used to reference plugins in schema configuration.

| Plugin type           | Base class                      | Role                                                                                                                                                                                                                    |
|-----------------------|---------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **ContextPlugin**     | `StageManagerContextPlugin`     | Provides data items to display (`get_items()`). One per stage manager. Has a `data_type` (NONE, USD, FILE) that constrains which listeners and interactions are compatible.                                             |
| **InteractionPlugin** | `StageManagerInteractionPlugin` | Represents a tab. Orchestrates tree, filters, columns, and widgets. Has `compatible_data_type` that must match the context. Declares `compatible_filters`, `compatible_trees`, and `compatible_widgets` for validation. |
| **TreePlugin**        | `StageManagerTreePlugin`        | Provides `TreeModel` (filtering, refresh, column count) and `TreeDelegate` (rendering, context menus). `TreeItem` represents individual items with display name, data, and optional nickname.                           |
| **FilterPlugin**      | `StageManagerFilterPlugin`      | Implements `filter_predicate(item) -> bool` and can override `_refresh_filter_active()` to update the `filter_active` field when its current UI state is neutral. The interaction collection that owns it determines the phase: `context_filters` and `internal_context_filters` run during context preparation, while `filters` and `additional_filters` run during user filtering. `display` controls UI only. Fires `_on_filter_items_changed` when the user changes parameters.             |
| **ColumnPlugin**      | `StageManagerColumnPlugin`      | Groups widgets horizontally in the tree. Has `display_name` and `width` (Fraction/Percent/Pixel). Implements `build_ui()` for cells and `build_header()` for column headers.                                            |
| **WidgetPlugin**      | `StageManagerWidgetPlugin`      | Individual cell widget inside a column. Implements `build_ui()` and `build_overview_ui()` (summary row). Fires `_on_item_clicked`.                                                                                      |
| **ListenerPlugin**    | `StageManagerListenerPlugin`    | Subscribes to data change events (USD stage changes, layer mutations). Has `compatible_data_type` that must match the context.                                                                                          |
| **MenuMixin**         | `StageManagerMenuMixin`         | Optional mixin for plugins that need context menus. Provides `register_menu()` / `unregister_menu()` lifecycle.                                                                                                         |

---

## Schema-Driven Configuration

Plugins are wired together via a JSON schema file. The schema path is set through `carb.settings` in the composition
extension's `extension.toml`:

```toml
[settings.exts."omni.flux.stage_manager.core"]
schema = "${lightspeed.trex.app.resources}/data/stage_manager_schema/default_schema.json"
```

### Schema structure

```json
{
  "context": {
    "name": "CurrentStageContextPlugin",
    "context_name": ""
  },
  "interactions": [
    {
      "name": "AllPrimsInteractionPlugin",
      "filters": [
        {"name": "SearchFilterPlugin"},
        {"name": "AdditionalFilterPlugin"}
      ],
      "context_filters": [
        {"name": "OmniPrimsFilterPlugin", "include_results": false},
        {"name": "IgnorePrimsFilterPlugin", "ignore_prim_paths": ["..."]}
      ],
      "columns": [
        {
          "name": "HorizontalColumnPlugin",
          "display_name": "Stage Prims",
          "widgets": [
            {"name": "PrimTreeWidgetPlugin"}
          ]
        }
      ]
    }
  ]
}
```

Plugins are referenced by class name. At startup, `StageManagerSchema._resolve_plugins_recursive()` instantiates
registered plugin classes from the JSON and validates compatibility (data types, filter/tree/widget constraints).

The real Remix schema lives at:
`source/extensions/lightspeed.trex.app.resources/data/stage_manager_schema/default_schema.json`

---

## Adding a New Plugin

1. **Choose the plugin type** from the table above.
2. **Create a class** extending the correct base (e.g. `StageManagerFilterPlugin`).
3. **Register in extension startup** via the factory:
   ```python
   from omni.flux.stage_manager.factory import get_instance as _get_factory_instance

   class MyPluginExtension(omni.ext.IExt):
       _PLUGINS = [MyCustomFilterPlugin]

       def on_startup(self, _):
           _get_factory_instance().register_plugins(self._PLUGINS)

       def on_shutdown(self):
           _get_factory_instance().unregister_plugins(self._PLUGINS)
   ```
4. **Add to the JSON schema** by name — the plugin's class name must match the `"name"` field in the schema.
5. **Declare `extension.toml` dependency** on `omni.flux.stage_manager.factory`.

---

## Flux / Lightspeed Layering

**Flux** provides all base classes and generic plugins:

- `omni.flux.stage_manager.core` — orchestration engine (`StageManagerCore`)
- `omni.flux.stage_manager.factory` — plugin registration (`StageManagerFactory`)
- `omni.flux.stage_manager.widget` — generic tree/tab UI widget
- `omni.flux.stage_manager.plugin.*` — generic plugins (search filter, USD context, tree structure, column layout, prim
  widgets, stage/layer listeners)

**Lightspeed** adds Remix-specific plugins:

- `lightspeed.trex.stage_manager.plugin.filter.usd` — capture filters (`IsCaptureFilterPlugin`), category filters (
  `IsCategoryFilterPlugin`)
- `lightspeed.trex.stage_manager.plugin.interaction.usd` — Remix interaction tabs
- `lightspeed.trex.stage_manager.plugin.tree.usd` — category groups (`CategoryGroupsTreePlugin`), mesh groups (
  `MeshGroupsTreePlugin`)
- `lightspeed.trex.stage_manager.plugin.widget.usd` — viewport actions (`FocusInViewportActionWidgetPlugin`), category
  assignment (`AssignCategoryActionWidgetPlugin`)

**`lightspeed.trex.stage_manager.widget`** is the **composition extension** — it depends on all Flux and Lightspeed
plugin extensions, sets the Remix schema path, and creates the UI:

```text
lightspeed.trex.stage_manager.widget (composition)
├── omni.flux.stage_manager.core
├── omni.flux.stage_manager.widget
├── omni.flux.stage_manager.plugin.* (all Flux plugins)
└── lightspeed.trex.stage_manager.plugin.* (all Remix plugins)
```

---

## Refresh Pipeline

Stage Manager has two refresh paths: context changes replace the tree generation, while user-filter changes project the
existing generation without rebuilding it.

### Filter execution phases

Reuse one filter when user filtering and context classification share the same domain rule. Lights, Custom Tags, and
Categories use neutral internal configurations of their canonical filters to prepare context items. Materials use a
separate internal binding filter because user filtering accepts meshes broadly while grouping retains only bound meshes.
Interaction wiring determines when each filter runs: schema-defined `context_filters` and interaction-owned
`internal_context_filters` run in the context worker after source collection and before `set_context_items()` and
canonical tree construction. Do not duplicate a filter solely to run it in this phase.

User filtering is a separate projection step. Only active plugins from the interaction's `filters` and
`additional_filters` run against the retained context items after canonical construction; enabled internal filters still
run during context preparation. A user-filter refresh changes the visible proxy hierarchy but does not redefine
interaction membership or rebuild the canonical tree.

Ancestor retention separates interaction permission, tree capability, and the effective result. An interaction uses
`allow_context_ancestors` to grant permission, while its selected tree uses `requires_context_ancestors` to state whether
it needs source ancestors. The context worker retains ancestors only when both are `True`:

| `allow_context_ancestors` | `requires_context_ancestors` | `include_context_ancestors` |
|---|---|---|
| `False` | Either | `False` |
| `True` | `False` | `False` |
| `True` | `True` | `True` |

Tree models require ancestors by default. Concrete grouped models set `requires_context_ancestors = False` because they
construct their own hierarchy. Setting `allow_context_ancestors = False` remains an interaction-level sparse-tree veto
for every compatible model.

### Refresh-owned prepared state

Every `StageManagerItem` owns typed prepared state for one full context refresh. Internal context classifiers mark
display-name candidates with `mark_display_name_candidate()` or store semantic results with `prepare_display_name()`
and `prepare_group_memberships()`; tree models consume those memberships without depending on the classifier's name or
repeating USD queries. Active user-filter configurations do not write this state. Do not use prepared state for shared
filter, model, or UI state, or as a long-lived cache.
`reset_filter_state()` retains prepared state for the wrapper's lifetime; destroying the wrapper clears it.

Context predicates remain ordered, short-circuiting, cancellable, and off-thread. An item rejected by a schema context
filter does not reach an internal classifier and therefore does not join the legacy display-name candidate set. An item
that reaches an internal classifier may still be marked as a display-name candidate before that classifier rejects it.
Do not add a whole-list `prepare_items()` pass: it would duplicate USD work, evaluate candidates rejected earlier, or
require another cache.

### Tree ownership

- Canonical items own the complete hierarchy and never change while user filters toggle.
- Each canonical item owns one proxy with independent parent/child links for the visible hierarchy. Proxy identity stays
  stable until a full refresh replaces the generation.
- TreeView, selection, expansion, and path lookups use proxies. Builders, menus, and actions explicitly unwrap
  `proxy.original_tree_item`; selection callbacks map canonical items back through `canonical.proxy`.
- Visible counts are published and reset together before the single global item notification, so
  `visible_items_count` and `visible_non_virtual_items_count` describe one visible generation. Counts include virtual rows
  and duplicate row occurrences; the non-virtual count excludes virtual rows but still counts each duplicate occurrence.
  The default recursive full-tree count uses the cached total, while explicit items or nonrecursive requests use the
  base traversal over the requested visible proxies. Base construction and projection periodically yield cooperatively
  while checking cancellation so long refreshes do not monopolize the worker.
- Remix's Stage Manager subscribes to the app-wide Ctrl+A event and invokes the active interaction's existing select-all
  behavior, regardless of mouse position. Selection traverses the published model and selects retained data-backed rows
  except `RootNode`. Synthetic virtual groups are excluded; hierarchy parents and descendants under collapsed branches
  are included. Text fields retain their native Ctrl+A behavior.

### Selection and framing

`_get_selection()` is the authoritative exact selection. The update loop highlights every visible proxy for each
selected path, including grouped duplicates. A retained hidden proxy for an exact selected path also counts as a match,
so it suppresses navigation fallback. `_get_framing_selection()` supplies related navigation candidates only; when no
exact proxy is available, the loop frames the first data-backed candidate in rendered sorted/filtered order. Custom Tags
and `get_extended_selection()` keep their existing behavior.

### Refresh paths

| | Full context refresh | Filter-only refresh |
| --- | --- | --- |
| Trigger | Context or context-filter change | User-filter change |
| Worker | Traverse USD, build a new canonical/proxy generation, then apply active filters. | Apply built filter predicates to retained context wrappers, then project the canonical hierarchy. |
| Publish | Replace the generation. Use `keep_alive_disabled()` through publication and one Kit update, restoring the prior value if the wrapper survives. | Reconnect existing proxies and publish visible indexes. Never call `_build_items()` or `refresh_model()`. |
| Identity | Canonical items and proxies are replaced. | Canonical topology, proxies, and selection remain stable. |

Context filters determine which wrappers reach `_build_items(items, cancel_event)`; user filters do not change its
canonical input. Clearing filters rebuilds the complete proxy hierarchy, including pathless and empty groups, from that
unchanged topology.

### Worker and publication contracts

- `ToggleableUSDFilterPlugin.filter_predicate(item)` is the final public template: it owns inactive pass-through and
  include/exclude inversion. Toggleable subclasses implement `_evaluate_item(item)` as a side-effect-free positive domain
  match. Other filters implement `filter_predicate()` directly. `build_filter_predicate(cancel_event=None)` is the single
  refresh-local builder: user filtering calls it without an event after skipping inactive filters, while context filtering
  supplies its cancellation event. A specialized builder may wrap `_evaluate_item()` for a neutral internal configuration
  and prepare only the refresh-owned item it evaluates. Configuration selects that preparation behavior; the event does
  not select an execution phase. Built predicates must not access `omni.ui` or mutate shared state. Ordinary filter
  settings do not need explicit snapshots: newer filter work supersedes stale work, so the last requested apply wins.
- Context filtering runs as one synchronous worker transaction. Each transaction owns a `WorkerYieldBudget` whose
  periodic checkpoints release the GIL while preserving cancellation checks. Intermediate validity, prepared-name,
  and parent mutations remain private to refresh-owned wrappers, and only a completed, uncancelled result is published
  atomically. Tree construction and proxy projection each own a separate budget; context filtering uses a longer GIL
  release than tree preparation to favor viewport responsiveness during its larger unit of work.
- Filter-only workers read canonical topology but do not mutate items, proxies, model fields, indexes, or UI before
  publication. Publication reconnects proxies and emits one global item notification.
- New context work cancels obsolete work, and newer filter work supersedes older filter work. Filter edits received
  during a context refresh are coalesced into its published generation; captured-root checks reject stale filter results.
- Filter-driven expansion is temporary and preserves the user's expansion cache. Pathless descendants of matching data
  remain visible; unrelated pathless groups remain only when they contain visible descendants.
- `_build_items(items, cancel_event)` treats context wrappers as read-only, assigns stable item paths, and returns `None`
  when cancelled. `get_items_by_path(path)` returns all currently visible proxies, including grouped duplicates.

Refresh telemetry spans worker execution through post-refresh work and records only trigger, status, and wrapper counts.
`input_items_count` is the post-context wrapper count passed to canonical construction, before user filtering;
`output_items_count` is the wrapper count retained after user filtering. These values are candidate counts, not canonical
or visible row counts.

---

## Key Extension Paths

| Extension                                              | Role                                                                                               |
|--------------------------------------------------------|----------------------------------------------------------------------------------------------------|
| `omni.flux.stage_manager.core`                         | Core orchestration — schema resolution, active interaction management                              |
| `omni.flux.stage_manager.factory`                      | Plugin registration and factory base                                                               |
| `omni.flux.stage_manager.widget`                       | Generic tabbed tree/table UI widget                                                                |
| `omni.flux.stage_manager.plugin.column`                | `HorizontalColumnPlugin` — horizontal widget grouping                                              |
| `omni.flux.stage_manager.plugin.context.usd`           | `CurrentStageContextPlugin` — provides USD stage items                                             |
| `omni.flux.stage_manager.plugin.filter.usd`            | `SearchFilterPlugin`, `AdditionalFilterPlugin`, `OmniPrimsFilterPlugin`, `IgnorePrimsFilterPlugin` |
| `omni.flux.stage_manager.plugin.interaction.usd`       | `AllPrimsInteractionPlugin` and other generic interaction tabs                                     |
| `omni.flux.stage_manager.plugin.listener.usd`          | USD stage and layer change listeners                                                               |
| `omni.flux.stage_manager.plugin.tree.usd`              | Generic USD tree structure plugins                                                                 |
| `omni.flux.stage_manager.plugin.widget.usd`            | Generic USD prim widgets                                                                           |
| `lightspeed.trex.stage_manager.widget`                 | **Composition** — depends on all plugins, sets Remix schema                                        |
| `lightspeed.trex.stage_manager.plugin.filter.usd`      | Remix capture and category filters                                                                 |
| `lightspeed.trex.stage_manager.plugin.interaction.usd` | Remix-specific interaction tabs                                                                    |
| `lightspeed.trex.stage_manager.plugin.tree.usd`        | Category/mesh grouping trees                                                                       |
| `lightspeed.trex.stage_manager.plugin.widget.usd`      | Viewport action and category assignment widgets                                                    |
