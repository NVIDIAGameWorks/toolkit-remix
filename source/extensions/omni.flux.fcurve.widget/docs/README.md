# omni.flux.fcurve.widget

Reusable bezier curve widget for rendering and editing function curves.
Decoupled from any storage mechanism -- bring your own persistence via callbacks.

## Responsibilities

- Render curves, keyframes, tangent handles, and infinity extrapolation.
- Apply bounded key and tangent edits and publish selection/edit events.
- Evaluate processed curves without changing their data.
- Prepare and apply shared offsets to selected keys while preserving live key identities.

## Non-Responsibilities

The widget does not own storage, USD commands, a channel tree, or toolbar-level undo grouping.
[The curve editor](../../omni.flux.curve_editor.widget/docs/README.md) supplies the surrounding editing interface;
callers supply persistence and edit-session callbacks.

## Architecture

- `FCurve` and `FCurveKey` hold curve data; key and tangent references describe selection.
- `FCurveWidget` manages displayed curves, editing, and callback delivery.
- `CurveWidgetsManager` builds handles and segments for one curve.
- `evaluate_curve` samples the processed tangent geometry used for display.

`FCurve` edits are storage-independent and obey caller-supplied property bounds. Kit's `omni.anim.curve.core`
`EditAnimCurveKeys` command supports absolute and additive edits to USD `AnimationSchema` curves, converting times
to integer ticks. It does not replace this widget's shared property and neighbor clamping: `prepare_key_offset()`
computes one legal selection offset, while `set_key_positions()` reuses the existing `process_curve()` tangent pipeline.

## Quick Start

```python
from omni import ui
from omni.flux.fcurve.widget import FCurveWidget, FCurve, FCurveKey, TangentType

# Build widget inside a ui context
with ui.Frame():
    widget = FCurveWidget(
        time_range=(0.0, 1.0),
        value_range=(0.0, 1.0),
        on_commit=lambda curve_id, curve: print(f"Commit: {curve_id}"),
    )

# Set curves to display
widget.set_curves({
    "my_curve": FCurve(
        id="my_curve",
        keys=[
            FCurveKey(time=0.0, value=0.0),
            FCurveKey(time=0.5, value=1.0, in_tangent_type=TangentType.SMOOTH,
                      out_tangent_type=TangentType.SMOOTH),
            FCurveKey(time=1.0, value=0.0),
        ],
        color=0xFF00FF00,
    ),
})
```

## Features

- Multiple bezier curves with independent colors and keyframe drag, add, delete, and multi-select
- Linked/broken tangent editing: LINEAR, AUTO, SMOOTH, FLAT, STEP, CUSTOM
- Pre/post infinity extrapolation (CONSTANT, LINEAR)
- `on_commit` callback for synchronous storage persistence
- `on_drag_started` / `on_drag_ended` callbacks for undo batching

## Key Editing

An initial left press selects an unselected key, replacing the current selection unless Shift is held. Shift adds the
key; pressing an already-selected key preserves the current selection. Movement and release do not change selection,
including when the pointer ends over another curve's key.

Dragging a selected key translates the editable selection through the shared offsets and constraints described under
[Batch Key Movement](#batch-key-movement), preserving relative key positions and selection. The widget captures the
selection and full curve baselines on the first native movement, after press-time selection has completed. Each
participating curve receives paired drag-started and drag-ended callbacks; the host owns grouped persistence.

`editable_selected_keys` returns a computed tuple of distinct, valid selected-key references on visible, unlocked
curves, preserving their first-occurrence order. It excludes missing curves and invalid indices without changing
`selected_keys`, emitting notifications, or writing storage. Numeric controls and selected-key actions share this
eligibility contract; raw selection remains available separately.

`delete_selected_keys()` deletes only selected keys on visible, unlocked curves and retains at least one key per
curve. It returns the number of deleted keys; no selection produces no data changes or edit notifications.
Tangent type, Link, and Break operations also affect only selected keys on visible, unlocked curves.

`set_selected_keys_tangent_type()` applies the requested sides to broken keys and both sides to linked keys,
using each editable selected key's own link state. Setting both `in_tangent` and `out_tangent` to `False` returns
`0` without changing data or emitting edit notifications, including for linked keys. Normal STEP normalization
and CUSTOM handle processing still apply.

Rebuilding the display, including after color or visibility changes, restores selection highlighting on visible
handles without creating storage edits.

Selected key and tangent handles brighten their curve color with gamma 6.0: each RGB byte becomes
`round(255 * (channel / 255) ** (1 / 6.0))`. Their native selected state adds a one-pixel black or white border so
colors that gamma cannot brighten, including white, black, and pure primaries, still have a selection cue. Both fill
and border preserve the curve's alpha. Deselection restores inherited border styling, and hover retains its existing
behavior. In version 3, custom `FCurveKeySelected` and `FCurveTangentSelected` background overrides no longer control
the selected fill; normal and hover styling retain their existing behavior.

`add_key()` processes and bounds the inserted key before key-added and commit notifications, so callbacks receive
the same key data used by the rebuilt display.

Segment containers receive presses because native curve callbacks can miss on-curve clicks. The manager rejects
background presses by first testing the native closest-parameter result against a six-logical-pixel hit radius.
After a Bezier miss or an endpoint estimate, it retries once at the pointer's model time using the shared inverse-time
calculation. Both candidates use the same radius; accepted insertion positions are within six logical pixels of the
pointer, not necessarily exactly beneath it. Successful native projections are preserved, including on steep curves.
The bounded retry is not a general nearest-point solver. STEP segments receive container presses and use the native
parameter without Bezier inversion. Accepted hits still pass the existing spacing and tangent-shape checks.

Handle presses claim the edit first. While `is_inserting_key` is true, the host's input poll calls
`update_insertion((x, y))` with canvas-local coordinates, then
`update_insertion(None)` on release or focus loss.
The parameter lookup uses device pixels; insertion dragging uses logical pixels, including at scaled DPI.
Key, tangent, and insertion gestures finish before manager replacement or destruction; destroy the widget before
releasing its storage callbacks.

## Version 2 Migration

`FCurveWidget.fit_to_data()` was removed in version 2.0.0. The
[curve editor canvas](../../omni.flux.curve_editor.widget/docs/README.md#toolbar-actions) owns framing and synchronizes
the rendered curves, grid, and rulers. Canvas hosts call `canvas.fit_to_data()`; standalone FCurve hosts assign
`time_range` and `value_range` directly.

## Curve Evaluation

Import `evaluate_curve` from `omni.flux.fcurve.widget` and pass a curve with keys ordered by time and processed
tangent offsets, such as a curve obtained from `widget.curves`:

```python
from omni.flux.fcurve.widget import evaluate_curve

value = evaluate_curve(widget.curves["my_curve"], 0.25)
```

Evaluation supports cubic Bezier segments, outgoing STEP tangents, exact key values,
single-key curves, and CONSTANT/LINEAR infinity behavior. Empty curves and non-finite requested times raise
`ValueError`. Sampling never mutates the curve; process raw tangent offsets before calling it.
Evaluation and insertion share the internal `bezier_parameter_at_time()` bisection, which uses at most 48 iterations
to invert a processed Bezier segment's time coordinate.

## Batch Key Movement

`prepare_key_offset(baseline, selected_keys, *, time_offset=0.0, value_offset=0.0)` returns target positions without
changing curves or calling storage. References are deduplicated and only visible, unlocked curves participate.
Each axis receives one shared offset, clamped by the tightest bound across the selection. Time also preserves the
minimum gap to unselected neighboring keys; adjacent selected keys retain their spacing.

Neighbor clamping preserves already-valid baseline times, including gaps accepted by the roundoff tolerance below.
Value-only edits leave key times unchanged, and a time edit blocked by a neighbor clamps to a zero time offset.

Preparation, validation, and normal curve processing share an absolute `1e-12` tolerance for minimum-gap roundoff.
Positive minimum gaps still require strictly ordered times; duplicate and reversed keys remain invalid. Property hard
bounds remain exact, and value clamping is unchanged. Processing preserves a requested time within those bounds when
its clamp difference and both neighbor-gap comparisons satisfy the tolerance, so accepted batch coordinates survive
repeated processing and manager rebuilds.

When larger floating-point errors prevent the requested time offset, preparation retains a finite search for a safe
shared offset derived from the selected keys. This fallback can take quadratic work in the number of selected keys
for dense minimum-gap selections. It is not a complete solver for every floating-point arrangement and raises
`ValueError` if none of its candidates is safe.

Capture `baseline` once at gesture start as a dictionary from curve IDs to copies of **every** `FCurveKey` in that
curve, including tangent fields. Reuse that same snapshot for every update. Moving a selected key can recompute
unselected neighbors' tangents, so copying only selected keys or accumulating offsets from current values is
insufficient. For an absolute edit, subtract the key's baseline coordinate before preparing the offset.

Call `set_key_positions(positions, *, baseline=baseline)` with the prepared targets. It validates all candidates
before mutating live data, processes each changed curve once, and copies the results into existing key objects.
Key lists, key identities, and selection indices remain stable. Renderer positions synchronize on the existing Kit
update subscription; each changed curve receives one synchronous commit callback after all live curves are updated.
All batch commit callbacks finish before curve-change events are delivered; callback failures propagate to the caller.
Unchanged effective positions do not commit. Invalid references, non-finite inputs, or malformed baseline data raise
`ValueError` without partially applying candidate curves.

The caller owns gesture lifetime, persistence, and undo grouping. Compare prepared coordinates with current values
before opening storage edits. With a backend that records commands at model finalization, group those finalizers
synchronously rather than keeping a global undo group open during input. Keep source curve and key identities
alongside the snapshot and stop the gesture if they change: a reference is an index, not a persistent key ID. Never
apply an old baseline after a storage reload. The
[curve editor](../../omni.flux.curve_editor.widget/docs/README.md#numeric-key-editing)
supplies this lifecycle for its numeric controls and groups finalization for native key drags.

## Further Reading

- [Architecture](ARCHITECTURE.md) -- tangent pipeline, layer constraints, data flow
- [Tangent Behavior](TANGENT_BEHAVIOR.md) -- tangent type rules, clamping, interaction matrix
