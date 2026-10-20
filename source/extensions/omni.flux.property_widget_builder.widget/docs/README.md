# Property Widget Builder

Build property panels from value models backed by USD, files, or other application data.

![Property widget](../data/images/preview.png)

## Responsibilities

- Display name and value models in a property tree with reusable field builders.
- Coordinate row selection, expansion, hidden primary rows, and linked fields.
- Centralize clipboard parsing, matching, structural checks, and synchronous paste in `AttributeCopyPasteHelper`.

## Non-Responsibilities

Value models own conversion, bounds, callbacks, validity checks, and authoring. Feature panels own their dialogs.
The helper does not provide rollback or manage delayed callbacks.

## Architecture

`ItemModelBase` supplies names or values through `get_value()` and existing setters. `Item` holds the ordered
`name_models` and `value_models`; these lists need not have equal lengths. `Model` owns the row tree, and `Delegate`
selects field builders and renders its two columns.
`ItemModelBase.is_virtual` is read-only and defaults to `False`; virtual models set protected `_is_virtual` to `True`.

`Delegate` owns the shared `DragFieldGroupCoordinator`. Builders returning an `AbstractDragFieldGroup` set
`supports_field_cleanup=True` and `builds_drag_field_group=True` to receive cleanup and linked-row coordination.
Pixel-sized name columns adjust to panel size without redrawing rows for an unchanged width.

### Clipboard and row editing

`Item` inherits `AttributeCopyPasteHelper`. Copy/Paste Selected and All use the same helper; All includes hidden
editable primary rows and excludes structural groups and claimed companions. The helper reads the clipboard once,
matches supplied destination rows, checks complete property membership and eligibility, and arranges values.
Existing models and commands still validate the values themselves, so later rejection can leave earlier writes applied.
Copy reads effective ordinary values through their models, preserving configured defaults without authoring the source.
Assets use the last selected source's raw value; logical rows retain raw backing values.
Serialization normalizes `Sdf.AssetPath` separators from `\` to `/` without resolving paths or requiring files to exist.
For USD rows, paste applies the destination stage's existing relative-path policy before calling the model setter.
The asset does not need to exist.

`Item.set_row_values(prepared_values)` accepts a tuple with one input per value model. It checks cardinality and
refreshes each model immediately before calling its existing setter. Logical USD rows provide the only other setter
implementation; their [ownership and authoring](../../omni.flux.property_widget_builder.model.usd/docs/README.md#logical-row-editing)
remain in the USD extension. Button-only logical outlets remain eligible without fabricated display models.

The helper disables linked editing before applying an accepted row, preserving distinct copied components. Linking
stays off after undo. A row rejected during clipboard checks retains its link state.

One helper-owned native undo group combines synchronous command-backed writes across rows and destination prims.
The helper opens no group when nothing is accepted. A standalone row setter does not promise one undo action; its
caller owns grouping when needed. Grouping does not guarantee rollback or make arbitrary setters undoable.
Texture/import callbacks that write after paste returns retain their existing undo timing and validity ownership.

Version 3 removes row serialization/application methods, `Serializable`, value-model paste/deserialization hooks,
and the free-function clipboard entry points. Old clipboard envelopes are rejected. Use the helper for clipboard
operations and `set_row_values()` for general row application; no compatibility wrappers are provided.

## Usage

```python
from omni.flux.property_widget_builder.widget.tree.clipboard import AttributeCopyPasteHelper

AttributeCopyPasteHelper.copy(source_rows=source_rows)
AttributeCopyPasteHelper.paste(target_rows=destination_rows)
```

Custom value models can use `set_display_fn()` to format stored values without changing them.
`PropertyWidget.expand_all_groups()` and `collapse_all_groups()` preserve the requested expansion state across
deferred refreshes. See the [USD model](../../omni.flux.property_widget_builder.model.usd/docs/README.md) and
[file model](../../omni.flux.property_widget_builder.model.file/docs/README.md) for concrete integrations.
