# omni.flux.property_widget_builder.delegates

`omni.flux.property_widget_builder.delegates` contains reusable property fields for items from
`omni.flux.property_widget_builder.widget`, including shared typed-value editors, file picker, and ComboBox controls.

## Responsibilities

- Build reusable property value fields and grouped numeric drag rows.
- Coordinate linked-row controls, value routing, focus, commit, cancel, unlink, and one-active-row behavior.
- Use item-owned linked state and value operations so rows remain linked across widget rebuilds.
- Owns temporary floating property windows, including preparation, selection dismissal, and cleanup.
- Composes generic Gradient editing content through `ColorGradientField`.

## Non-Responsibilities

- Does not author USD or implement USD multi-selection, refresh, or failure recovery. The USD property model owns
  those operations through its item and value models.
- Does not choose which field represents an item. Property-widget models and field-builder registrations own that
  mapping.

## Architecture

Subclass `AbstractField` and implement `build_ui()`. Prefer an existing shared field before adding a product-specific
editor.
The hosting application supplies the inline Gradient's named `ColorGradientBar` and `ColorGradientBarOverlay` styles.
`FilePicker` accepts stable field and picker identifiers. Relative-path pickers must also provide the
keyword-only `stage_resolver` callback; constructing `FilePicker(use_relative_paths=True)` without that explicit USD
stage capability raises `ValueError`. `ComboboxField` consumes an `ui.AbstractItemModel` supplied by the property
value model.

`ColorField` owns the color model shared by its read-only component fields and `ColorPicker`, a Frame-based RGB/RGBA
editor with live updates. The picker provides saturation/value and hue controls, RGB/HSV numeric fields, hex input,
and a Current preview. All picker edits use normalized `[0, 1]` channels, including alpha and HSV Value; each new
color clamps the whole RGB/RGBA vector. Opening, external refresh, and Undo preserve existing HDR or negative
authored values. `display_precision` only formats the read-only row. Read-only fields disable the picker.
The swatch uses app-defined Rectangle name selectors; shared delegate style updates set its name and selected state.

Hex input accepts `RRGGBB` or `RRGGBBAA` with an optional `#`, or parenthesized normalized RGB/RGBA tuples matching
the color's channel count. Tuple channels must be finite numbers in `[0, 1]`. Text commits on end-edit or dismissal;
invalid input preserves the current color and undo history. Formatting hex does not change authored HDR values.

Picker-owned events define each gesture and send complete RGB/RGBA colors to the backing model. With a batch-capable
backing model, held drags preview the color and each mouse release or completed typed edit commits one Undo entry
when the color changes. Removing the row retains its latest preview. External edits or Undo discard interrupted input
so stale input cannot overwrite the restored color.
Rows rebuilt during a gesture display the model's cached preview while its USD write is pending.

`ColorPickerPopup` adapts the shared [`FieldPopupWindow`](#floating-property-editors) lifecycle. The USD field builder
supplies `context_name` for selection dismissal; generic fields can omit it. Normal dismissal commits pending input,
while cancellation discards it. The picker borrows its model and adds no separate global input listeners.
The popup opens at a fixed default size. Its gradient and input column fill the available content area when resized;
the hue bar and Current column retain their widths. The shared host handles viewport placement and clamping.
Content is arranged in a main editing column and a Current preview column, with local gradient-handle overlays,
eight pixels of padding at the top and sides, and sixteen pixels below Hex.
Numeric rows use one horizontal stack with fixed label widths and equally expanding input fields.
SVG handles use fixed-size frames inside full-area placers to preserve their size and movement during live edits.

Pass `register_cleanup` to `ColorField.build_ui()` to register `cleanup()` with the owning property widget, or call
`cleanup()` when releasing the field. The default USD builder registers it with the delegate. Cleanup releases the
picker, color model, and subscriptions even when ending an edit raises; the error still propagates.

`AbstractDragFieldGroup` builds and coordinates numeric fields in one row. Pass `linkable=True` to opt a Float or Int
group into link controls, linked presentation, focus, commit, cancel, unlink, and value routing. The item owns the
authoritative linked state and value operations. `DragFieldGroupCoordinator` keeps one row linked within a property
panel and resolves deferred focus against the newest visual build after tree virtualization rebuilds a row. Linked
state persists across focus changes and ends only when explicitly unlinked or when another row is linked.

`AbstractDragFieldGroup` owns the shared linked typed-editor lifecycle. `FloatDragFieldGroup` and
`IntDragFieldGroup` provide only their native numeric model, field, and value-conversion hooks. Domain-specific items
can override the standard linked-state and value-operation methods when they require atomic writes, undo, refresh, or
failure recovery.

### Floating Property Editors

`FieldPopupWindow` owns transient native windows; editing content remains Frame/Stack-based. Launchers capture their
bounds before optional preparation and call `open(preferred_size=..., anchor_rect=...)`. Only the latest ready request
opens after the outgoing window is destroyed; superseded queued requests close immediately. One popup is active
application-wide.

The window opens beside its launcher, clamps to the workspace, and centers without a usable anchor. Active close hides
it immediately and releases content on the next update; pre-activation cancellation cleans up immediately. Concrete
editors own models and sessions, and release hooks handle canceled or partial builds.

`context_name=None` skips selection observation, `""` observes the default USD context, and a nonempty name observes
that context. Selection changes cancel preparation or close the editor; any outside mouse-button press also closes it.
Escape closes the active editor and any open child picker without clearing the scene selection.
Application Ctrl+Z/Ctrl+Y remain available. The active host owns an application-level Escape subscription and checks
mouse-button transitions and pointer bounds on application updates for outside-click dismissal. These shared watches
are released when the editor closes; color controls add no separate global input listeners.

Editors extend `_on_key_pressed(key, modifiers, is_down)` and call `super()` to preserve Escape dismissal. This native
window callback follows keyboard focus; a widget's key callback follows pointer dispatch and is unsuitable for
window-wide shortcuts. Respect `ui.Widget.FLAG_WANT_CAPTURE_KEYBOARD` so text and numeric editing keep their keys.
Native mouse gestures also set this flag; an editor may distinguish its own active gesture using existing state
before deciding whether to handle the shortcut.

`ColorGradientField` retains its model and shared
[`GradientPreview`](../../omni.flux.utils.widget/docs/README.md#gradient-content) and subscribes to model changes for
the field's lifetime. Grouped model notifications, including external edits, refresh the inline preview while the
editor is closed or the field is read-only. Each `GradientFieldEditor` opening owns its session and controls. Destroying
the field releases its subscription without closing an active popup. The removed `style_name` argument makes `title`
the sixth positional argument.

A standalone USD-backed model without an active session does not observe USD changes on its own. Reopening the editor
loads the current payload. A normal USD property host can also refresh the inline preview by reconstructing the field
when it rebuilds the property row.

Clicks inside Gradient's picker or preset menu preserve the parent editor. Clicking back in the editor dismisses the
child; clicking outside both closes the editor. Selecting a preset closes its menu and keeps the editor open.

## Known Limitations

The native Gradient picker does not dismiss on an outside middle-click (REMIX-6105). Selection changes still dismiss
the property editor.
