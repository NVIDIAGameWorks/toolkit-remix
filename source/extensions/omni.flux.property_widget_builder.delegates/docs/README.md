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

`ColorField` owns the Python color item model shared by the read-only RGB fields and `ColorPicker`, an embedded
`ui.Frame`. `ColorPicker` owns the swatch, editor controls, color conversions, and gesture callbacks.
The same-extension `ColorPickerPopup` (`ui.Window`) owns popup creation, identity, positioning, local keyboard,
focus, and visibility dismissal notifications, and deferred native window teardown.
Each opening uses a fresh native window identity so the new popup cannot inherit held input from a retired popup.
The popup opens above the field when there is not enough room below it and moves left near the main window's right
edge. Its padded layout uses the application's `WorkspaceBackground` style. The wider property swatch opens a larger
saturation/value square and hue bar, with RGB/A, HSV/A, and hex fields aligned beneath them. The Current preview sits
in a separate column on the right. Clicking outside the popup or pressing Escape dismisses it without a Close button.
The picker borrows that model; the field retains its component models and subscriptions for the row's lifetime.
Saturation/value and hue controls define each gesture through widget-local press, move, and release callbacks.
Control-local coordinates map those gestures to colors. Each component's native `ui.FloatDrag` reports its own
begin/end edit boundary for dragging and typed edits.

The popup provides RGB/A and HSV numeric editors, a hexadecimal field, and a Current preview. Hue and Saturation
are normalized to `[0, 1]`; Value supports nonnegative HDR floats through typing and dragging.
Numeric fields apply valid changes live. Hex text is buffered until end-edit or dismissal.
Hex input accepts `RRGGBB` for RGB or `RRGGBBAA` for RGBA, with an optional `#` prefix. Its display clips and rounds
channels to bytes without changing authored HDR values; committing a valid hex edit writes each byte divided by 255.
The same field accepts parenthesized, comma-separated normalized tuples matching the active color's channel count:
three for RGB or four for RGBA.
Whitespace is allowed; each channel must be a finite number in `[0, 1]`, inclusive. RGB `(1.0, 1.0, 1.0)` becomes
`#FFFFFF`, and `(1.0, 0.5, 0.0)` becomes `#FF8000`; RGBA `(1.0, 0.5, 0.0, 0.5)` becomes `#FF800080`.
Tuple input uses Kit's eight-bit rounding, restores uppercase hex text, and commits changed colors as one undo operation.
Malformed input, wrong channel counts, booleans, nonnumeric values, and nonfinite or out-of-range channels are rejected.
Invalid input restores the formatted current color without changing authored values, including HDR, or undo history.
The Current preview is solid for RGB and splits RGBA into opaque and transparency-over-checkerboard halves.

Gradient image providers are created when the popup first opens. Saturation/value textures are regenerated only
while that image is visible and its hue changes. Closed pickers keep swatch and color synchronization without
generating or uploading hidden gradients. The saturation/value selector is a hollow white ring with a dark
outline so the color beneath it remains visible. White triangles with dark outlines point inward from both hue-bar
edges to mark the selected hue. Both marker placers use stable sizing so their movement does not resize the controls
or change the pointer-to-color mapping. Fixed picker dimensions and spacing use the application's four-pixel grid.
Widget-local image content-size callbacks position selectors from the retained HSV values after layout, so reopening
shows the current color. Marker updates use positive measured bounds and ignore callbacks from retired popups;
layout callbacks only move the selectors.

For models that support batch editing, each completed drag or typed edit uses a separate `begin_batch_edit(live=True)`
batch and produces one undo entry when the value changes. Opening the popup creates no undo entry.
The field pairs the backing model's `begin_edit()` and `end_edit()` for each gesture, deferring application refreshes
while authored colors remain live. RGB changes are combined into one complete-color write per application frame,
with a synchronous final flush when the gesture ends.
Normal close requested from an HSV component-change callback completes the remaining RGB writes before committing
that single gesture. Cancellation abandons remaining writes from the retired popup.

Undo while the popup is idle restores the previous gesture's color and leaves the picker ready for the next gesture.
Backing color updates notify the picker after all RGB/A components are synchronized, so temporary channel combinations
cannot replace its remembered hue when restoring white, gray, or black.
During an active edit, queued writes check the latest key from Kit's public command execution history before
authoring. Its monotonically increasing key detects intervening commands even if Undo and Redo restore the same
undo-stack boundary. An interrupted active edit discards buffered input and closes the popup while preserving the
restored backing color and the field's models and subscriptions.

Pass `register_cleanup` to `build_ui()` to register `cleanup()` with the owning property widget, or call `cleanup()`
directly when releasing the field. Cleanup releases subscriptions, the owned picker, and the owned color model even
when ending the backing edit raises; the lifecycle error still propagates.
The default USD color builder registers this cleanup with its delegate. A full delegate reset releases the field's
subscriptions even when its backing value model remains alive; picker cancellation keeps the current field usable.
`ColorPicker.destroy()` clears its borrowed component references and its saturation/value, hue, and checkerboard
image-provider references. Retired `_PickerValueModel` proxies disable writes and subscriptions but retain their
borrowed parents for safe late native getters throughout the popup owner's deferred teardown.
Read-only color fields disable the picker.
`display_precision` formats the read-only row text and does not set the picker's drag increments.

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
Application Ctrl+Z/Ctrl+Y remain available.

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
