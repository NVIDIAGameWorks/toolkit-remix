# omni.flux.curve_editor.widget

General-purpose bezier curve editor for Omniverse. Edit keyframes, tangent handles, and infinity modes through a pluggable `GroupedKeysModel`.

## Responsibilities

- Compose the channel tree, curve canvas, rulers, editing toolbar, and numeric key controls.
- Keep channel visibility and key selection separate from stored curve payloads.
- Convert between `FCurve` data and the pluggable `GroupedKeysModel` storage contract.

## Non-Responsibilities

USD persistence and property-panel sessions belong to
[the USD property model](../../omni.flux.property_widget_builder.model.usd/docs/README.md).
Curve rendering and tangent calculations belong to
[the FCurve widget](../../omni.flux.fcurve.widget/docs/README.md).
The editor does not require a timeline or author channel selection to storage.

## Architecture

- `CurveEditorWidget` connects storage, layout metadata, and edit contexts for toolbar actions and numeric gestures.
- `CurveTreePanel` publishes selected channel IDs using native tree multi-selection.
- `CurveEditorCanvas` loads the selected subset into `FCurveWidget` and commits edited payloads.
- `CurveEditorToolbar` prepares shared-time key additions, applies actions to selected keys, and exposes axis framing.

The canvas background input receiver stays last in its outer `ZStack`, with `send_mouse_events_to_back=True`, so
keys, tangents, and curve insertions claim their gestures before background deselection runs.

Keys support drag, add, delete, and copy. Tangent types are LINEAR, AUTO, SMOOTH, FLAT, STEP, and CUSTOM;
infinity modes are CONSTANT and LINEAR. Drag edits use single-entry undo hooks on the storage model.

## Quick Start

```python
from omni import ui
from omni.flux.curve_editor.widget import CurveEditorWidget
from omni.flux.curve_editor.widget.payload import curve_to_payload
from omni.flux.fcurve.widget import FCurve, FCurveKey
from omni.flux.utils.widget import InMemoryGroupedKeysModel

model = InMemoryGroupedKeysModel()
model.commit_payload("curve", curve_to_payload(FCurve(id="curve", keys=[FCurveKey(0, 0), FCurveKey(1, 1)])))

with ui.Frame():
    editor = CurveEditorWidget(model=model, time_range=(0, 1), value_range=(0, 1))
```

## Channel and Key Selection

Left-click a key to select it immediately, or Shift-click to add it to the selection. Pressing a selected key keeps
the selection, highlight, and editing controls active through dragging and release.

Dragging any selected key moves all selected keys on visible, unlocked curves by the same time and value offsets.
Their relative positions stay unchanged; the tightest property bound or unselected neighboring key limits the whole
selection. With the USD backend, one Undo restores the entire gesture and one Redo reapplies it.

Left-click empty canvas to clear key selection and disable selection-dependent controls. Shift, Ctrl, Alt, or Super
preserve selection on blank clicks; Caps Lock and Num Lock do not prevent deselection. Background clicks during a
curve gesture or pan preserve selection. Deselection does not change curve payloads or undo/redo history.

Opening an editor with a channel layout selects every channel and starts with every group expanded. Groups can be
collapsed manually. Click a channel row to show only its curve; Ctrl-click toggles individual channels and Shift-click
selects a range. Clicking a group selects its descendant channels. Clearing channel selection leaves the canvas empty.

Channel selection survives storage refreshes, undo/redo, and external edits, and resets when the editor is recreated.
It never writes payloads or creates undo entries. Filtering retains selected keys on displayed channels and removes
hidden keys from selection; storage reloads may clear key selection.

`editor.fcurve_widget.curves` contains only the displayed subset. Use `editor.model.group_ids` for the full storage
inventory. Without a channel layout, the editor displays all model curves.

Numeric fields and selected-key toolbar actions use `FCurveWidget.editable_selected_keys` for their shared eligibility
filter. The [FCurve widget](../../omni.flux.fcurve.widget/docs/README.md#key-editing) owns validation and ordered
deduplication of these references; the editor retains ownership of channel filtering and edit lifetimes.

### CurveTreePanel v2 Migration

Version 2 replaces `CurveTreePanel(on_visibility_changed=...)` with `on_curves_selected`. The callback receives the
complete selected channel ID set (`set[str]`) instead of a channel ID and visibility flag. Its initial notification
includes all channels. Forward the set directly to an existing canvas:

```python
from omni.flux.curve_editor.widget.panels import CurveTreePanel

panel = CurveTreePanel(layout, on_curves_selected=canvas.set_selected_curve_ids)
```

## Channel Styling

Each layout leaf (`CurveEntry`) accepts an optional `display_color` in `0xAABBGGRR` format and an optional
`label_style_name`, such as `CurveEditorChannelX`. Use a bare widget name without the `Label::` prefix. Style names
apply only to leaves; numeric group colors continue to inherit through the hierarchy.

`display_color` sets normal label and curve colors; `label_style_name` selects application rules such as
`Label::CurveEditorChannelX:selected`. Unnamed leaves use `CurveEditorChannel`. Direct callers supply both fields
for matching colors: the editor neither resolves stylesheet colors nor chooses a selection palette.

Labels expose their native selected state; deselection restores normal color, with empty channels at half alpha.
Selected styles affect only labels. Property controls use the
[USD layout adapter](../../omni.flux.property_widget_builder.model.usd/docs/README.md#curve-layout-styling) for normal colors.

## Toolbar Actions

**Add Key** targets every displayed, unlocked channel that already contains keys. It chooses one shared time from
the first eligible selected key: halfway to its next key, or `0.1` later when it is the last key. With no eligible
selected key, it uses the first eligible curve's first interval, or its sole key plus `0.1`.

Each new value is evaluated on that channel's curve at the shared time. A key already at exactly that time is reused.
All new and reused keys become selected. Before making any changes, Add checks every target's bounds, finite sampled
value, and minimum key spacing. If any target fails, the entire addition is unavailable and its tooltip explains why.
Locked and empty channels are skipped; use a channel's Create control to initialize empty curve data.

Delete follows the [FCurve selected-key deletion contract](../../omni.flux.fcurve.widget/docs/README.md#key-editing).
Tangent type and tangent locking act on selected editable keys; Shift-click keys to select more than one.
The tangent-lock toggle is pressed with a linked icon when all editable selected keys are locked, and unpressed
with a broken icon when they are unlocked. Click to switch between these states. A mixed selection shows the broken
icon and a mixed-state tooltip; clicking locks all editable selected keys. The toggle is disabled when no editable
keys are selected. Keys on hidden or locked curves and missing or invalid key references do not determine its state
or receive edits. The toggle reflects the selection remaining after the action, including changes by host callbacks.
Tangent type changes use each selected key's own link state, including mixed selections: linked keys change both
sides, while broken keys change only the clicked side. Normal STEP and CUSTOM tangent processing still applies.

**Frame Time** fits the horizontal axis and **Frame Value** fits the vertical axis, each preserving the other range
exactly. Both use every key on displayed curves, including offscreen keys and visible locked curves, regardless of
key selection. Hidden and channel-filtered curves do not contribute. Clicking both in either order matches full
framing; repeated clicks are stable. Framing preserves curve data, key selection, and undo/redo history.

Framing uses key bounds, excluding tangent handles and curve overshoot. Each requested axis receives 10% of its span
as padding on either side, or `0.1` on either side when its span is zero. Empty data preserves the current viewport.
`CurveEditorCanvas.fit_to_data(frame_type: FrameType = FrameType.ALL)` computes these bounds and synchronizes the
curves, grid, and rulers. Pass `FrameType.TIME` or `FrameType.VALUE` positionally or by keyword to frame one axis;
the default and `editor.fit_all()` fit both.

```python
from omni.flux.curve_editor.widget.canvas import FrameType

canvas.fit_to_data(FrameType.TIME)  # Fit time while preserving the value range.
canvas.fit_to_data(frame_type=FrameType.VALUE)  # Fit value while preserving the time range.
canvas.fit_to_data()  # Fit both axes.
```

Standalone toolbar callers can supply optional keyword-only `on_frame_time` and `on_frame_value` callbacks;
each supplied callback adds its button.

Hosts can call `editor.delete_selected_keys()` to use the same grouped edit as the toolbar, including with
`show_toolbar=False`. The host window routes the keyboard shortcut; the reusable editor installs no global handler.
Deletion finishes an active curve insertion first and does nothing during an ordinary key or tangent drag.

Click directly on a curve to insert a key without changing its shape. Keep the mouse button held to drag the new
key's time and value, then release to finish one undo action. Shape preservation may convert affected tangents to
Custom; undo restores their original settings along with removing the key.
Hit detection belongs to the [FCurve widget](../../omni.flux.fcurve.widget/docs/README.md#key-editing), including its
fallback for coarse native Bezier samples and the unchanged six-logical-pixel acceptance radius.

Info logs explain clicks rejected because key times are too close or a shape-preserving split exceeds tangent limits,
and confirm insertion finishes at its last valid position when the application loses focus; normal releases and
background clicks stay silent.

## Numeric Key Editing

Drag or type into the **Time** and **Value** fields at the bottom-right of the editor to edit selected keys.
Only selected keys on visible, unlocked curves participate.

| Eligible selection | Time field | Value field |
| --- | --- | --- |
| No keys | Disabled | Disabled |
| One key | Absolute time | Absolute value |
| Multiple keys | Time Offset | Value Offset |

An offset adds the same amount to every participating key's coordinate at the start of the gesture. Offsets reset to
zero when the edit ends; the next gesture starts from the updated keys. Both fields display five decimal places.
Drag speed follows the corresponding viewport span and stays fixed during each gesture.

Both axes respect each curve's property hard limits. Time also preserves the minimum gap to neighboring unselected
keys. Adjacent selected keys move together without changing their spacing. The tightest limit stops the whole
selection, including selections spanning several curves. These constraints apply to typed input as well as dragging;
the field reflects the applied coordinate or offset.

Effective changes update curves and backing storage continuously, before release. Completing the field edit with
release, Enter, or focus loss finalizes the gesture. With the USD backend, one Undo restores every participating
curve and tangent, including distinct original values across mixed prim targets; one Redo reapplies the gesture.
Pressing Ctrl+Z while holding a changed numeric drag cancels the whole drag immediately. Further pointer movement
and release cannot reapply it, and one scene Redo restores it. Ctrl-click text entry retains native text Undo/Redo,
including while selecting text with the mouse held.

Clicking a field, entering its current value, or dragging against a limit without moving preserves undo and redo
history. With the USD backend, a gesture that returns every target's complete payload to its starting state creates
no final command and preserves pending Redo. Returning only the displayed source coordinates to their starting values
can still leave mixed targets changed and therefore creates an undoable edit. Held-drag cancellation checks for a new
history entry before undoing, preserving earlier history when finalization records nothing.

Changing the channel filter or closing the editor finishes the active gesture. External storage changes invalidate
numeric input, rejecting subsequent field updates and held-drag cancellation. Finalization and reload are deferred to
the next Kit update. The backend's existing concurrent-edit semantics still apply; this does not isolate concurrent
commands, structural edits, or authored-layer changes. See the
[USD backend limits](../../omni.flux.property_widget_builder.model.usd/docs/README.md#floating-property-editors).

## Storage Backend

`GroupedKeysModel` from `omni.flux.utils.widget` stores suffix-keyed payloads containing `times`, `values`, tangent
arrays, and infinity tokens; the editor converts them to and from `FCurve` objects.

`GroupedKeysModel.subscribe()` delivers external changes. Backends own suppression of self-authored notifications:
the in-memory model stores edits without notifying, and the USD model suppresses its own write and finalization
notices. The canvas forwards external changes to the editor, or reloads storage when used standalone; its existing
viewport-drag reload suppression remains in place.

The optional `edit_context_factory: Callable[[], AbstractContextManager]` creates a fresh context for modifying toolbar
actions and discrete deletion. It defaults to `contextlib.nullcontext` for in-memory callers. The trailing optional
`finalization_context_factory: Callable[[], AbstractContextManager] | None = None` supplies the context for numeric
gesture finalization and is forwarded to the canvas's existing `edit_context_factory` argument. When omitted, it uses
`edit_context_factory`, preserving existing callers. Discrete actions continue to use the original factory even while
model edits are pending.

The [USD field builder](../../omni.flux.property_widget_builder.model.usd/docs/README.md#floating-property-editors)
provides grouped undo for discrete actions and a storage-aware finalization context for gestures. It avoids opening
an undo group when every target's complete payload is unchanged, preserving pending Redo.

Numeric gestures enter `CurveEditorCanvas.edit_curves()` on the first effective change and keep those model edits
open across input updates. Each successful model begin is finalized once. After flushing the final field value, the
editor clears its active gesture state and enters the finalization context only while synchronously closing those
model edits. No global undo group spans input frames. The USD backend groups changed per-channel commands,
preserving each target's original payload for undo. External model notices invalidate the numeric gesture.
Rendering uses the existing dirty-position update subscription without delaying storage writes.

Canvas key drags open model edits for each participating curve. Changed drags across multiple curves group their
finalization through the supplied finalization factory; clicks and fully clamped drags preserve redo. The canvas
closes all participating edits together on release or teardown; no global undo group stays open between pointer updates.

Owners must call `editor.destroy()` before destroying its storage model. Cleanup finalizes active edits and releases
field model subscriptions, native key callbacks, and deferred callbacks before destroying the owned canvas. Canvas
cleanup releases subscriptions and detaches active viewport edits before finalizing them and destroying its widgets.
Both cleanup paths release the remaining children even if a finalizer fails; repeated destruction is safe. The editor
owns the fields' key handlers; it adds no global input subscription. The USD `CurveFieldEditor` follows this cleanup
order through its `FieldPopupWindow` release hook.

## Further Reading

- [Architecture](ARCHITECTURE.md) - component hierarchy, data flow, drag system
