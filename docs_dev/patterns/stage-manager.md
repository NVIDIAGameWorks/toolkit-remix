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
| **FilterPlugin**      | `StageManagerFilterPlugin`      | Implements `filter_predicate(item) -> bool`. User-visible filters appear in the UI; context-only filters (`display=False`) run silently. Fires `_on_filter_items_changed` when the user changes parameters.             |
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
