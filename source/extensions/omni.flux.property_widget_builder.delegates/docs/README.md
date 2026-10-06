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
remains open, then writes the final color synchronously when the picker closes.
For models that support batch editing, it uses `begin_batch_edit(live=True)` so the model owns the picker session's
undo step and failure recovery. Other models use a Kit undo group. It forwards `begin_edit()` and `end_edit()` to
the backing model once per session so the model can defer expensive application refreshes while live values change.
The session ends when the picker closes.
Pass `register_cleanup` to `build_ui()` to register `destroy()` with the owning property widget, or call `destroy()`
directly when releasing the field. Field cleanup and property edit cancellation release subscriptions and close any
active picker session. Cleanup and external backing-value changes discard queued updates so stale picker values
cannot be written later. Read-only color fields disable the picker.
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
