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

`ColorField` combines the picker's RGB component changes into one complete-color update per frame while the picker
remains open, then writes the final queued color synchronously when the picker closes.
Callbacks reuse the component value models captured when the row is built, avoiding native item lookups during edits.
One picker item-change subscription feeds one deferred update path. Pending Undo dismissal takes priority over a
mouse-release checkpoint, which includes the latest color write; ordinary changes request only a color write.
For models that support batch editing, it uses `begin_batch_edit(live=True)` so the model owns each released drag's
undo step and failure recovery. Other models retain their own write behavior.
It forwards `begin_edit()` and `end_edit()` to the backing model once per session so the model can defer expensive
application refreshes while live values change.
Each mouse release finishes the current undo batch. An empty live batch then watches for external changes without
creating an undo step.
Keyboard edits share a batch until the next mouse release or popup dismissal; the backing edit session ends when the
picker closes.
Pass `register_cleanup` to `build_ui()` to register `cleanup()` with the owning property widget, or call `cleanup()`
directly when releasing the field. Cleanup releases subscriptions and closes any active picker session.
Property edit cancellation closes the backing edit session while retaining the field subscriptions. Cleanup and
external backing-value changes discard queued updates so stale picker values cannot be written later.
Undo dismisses an open picker after restoring its color; reopening starts a fresh edit session.
An external change cancels an open picker edit; close and reopen it before making another edit.
The cancellation guard rejects buffered input until the native popup opens again, preserving restored colors and redo.
Read-only color fields disable the picker.
Row cleanup is required even when the backing value model remains alive after a delegate rebuild.
The native picker reports individual component changes rather than a complete-color event during dragging.
The picker uses `ui.ColorWidget`'s native numeric dragging. `display_precision` formats the read-only row text and
does not set the picker's drag increments.

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
