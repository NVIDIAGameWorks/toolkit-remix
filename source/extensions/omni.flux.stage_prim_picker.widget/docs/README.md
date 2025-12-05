# omni.flux.stage_prim_picker.widget

Searchable dropdown widget for selecting USD stage prims in property panels.

## Features

- **Searchable dropdown** with real-time filtering
- **Schema-based filtering** to show only specific prim types
- **Path pattern filtering** to limit prims to specific subtrees
- **Pagination/Infinite scroll** with "Show More" for large hierarchies
- **Clear button** to remove selection
- **Framework integration** - automatic builder for `USDRelationshipItem`

## Standalone Usage

```python
from omni.flux.stage_prim_picker.widget import StagePrimPickerField

picker = StagePrimPickerField(
    context_name="",
    prim_filter=lambda p: p.GetTypeName() == "Mesh",  # Optional filter
    path_patterns=["/World/**"],  # Optional path restriction
    initial_items=50,
)
```

## Property Widget Framework Integration

When using `USDRelationshipItem`, the picker is built **automatically** by the framework.
Just pass `ui_metadata` when creating the item:

```python
from omni.flux.property_widget_builder.model.usd import USDRelationshipItem

item = USDRelationshipItem(
    context_name,
    relationship_paths,
    ui_metadata={
        "path_patterns": ["/RootNode/meshes/mesh_HASH/**"],
        "prim_filter": lambda p: p.GetTypeName() in ["Mesh", "Xform"],
        "initial_items": 50,
        "header_tooltip": "Pick a prim under this asset",
    },
)
```

### Supported `ui_metadata` keys

| Key | Type | Description |
|-----|------|-------------|
| `path_patterns` | `list[str]` | Glob patterns to filter prim paths |
| `prim_filter` | `Callable[[Prim], bool]` | Custom filter function |
| `prim_types` | `list[str]` | Schema type names to include (I.e: "UsdGeomMesh") |
| `initial_items` | `int` | Items before pagination (default: 20) |
| `header_tooltip` | `str` | Text shown at top of dropdown (e.g., "Pick your material...") |
