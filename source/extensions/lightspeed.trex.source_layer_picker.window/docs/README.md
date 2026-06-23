# lightspeed.trex.source_layer_picker.window

Utility widget for selecting which replacement source layers participate in edit-state filtering.

## Responsibilities

- Provides the `SourceLayerPicker` window used by callers that need to select replacement source layers.
- Presents the USD layer tree with picker-specific checkboxes for replacement-layer rows.
- Keeps search filtering, row checkbox rendering, and staged selection state local to the picker.

## Non-Responsibilities

- Does not decide which layers are replacement layers; callers provide that layer-id set.
- Does not filter Stage Manager prims directly; the Stage Manager filter plugin applies the picker selection.
- Does not mutate USD layers or layer-tree structure; the reused layer tree is configured read-only.
- Does not register an extension startup/shutdown class; callers import and own picker instances directly.

## Architecture

`SourceLayerPicker` builds the window and owns the draft selection that is applied only when the user clicks Select.
`SearchableLayerModel` subclasses the shared USD layer-tree model to filter visible tree rows by layer basename.
`SourceLayerPickerDelegate` subclasses the shared layer-tree delegate to hide layer-management affordances and render
checkboxes only for caller-provided replacement layer identifiers.
Callers update `mod_layer_ids` / `selected_ids` as properties and subscribe to the applied-selection event.

## Usage

```python
from lightspeed.trex.source_layer_picker.window import SourceLayerPicker

picker = SourceLayerPicker(
    context_name="",
    mod_layer_ids=frozenset({"mod.usda"}),
    selected_ids=None,
)
selected_ids_applied_sub = picker.subscribe_selected_ids_applied(lambda ids: None)
picker.show()
```
