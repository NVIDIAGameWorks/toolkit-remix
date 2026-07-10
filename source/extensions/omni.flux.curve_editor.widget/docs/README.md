# omni.flux.curve_editor.widget

General-purpose bezier curve editor for Omniverse. Edit keyframes, tangent handles, and infinity modes through a pluggable `GroupedKeysModel`.

No dependency on `omni.anim`, `omni.timeline`, OmniGraph, USD, or property-panel concepts.

## Quick Start

```python
from omni.flux.curve_editor.widget import CurveEditorWidget
from omni.flux.curve_editor.widget.payload import curve_to_payload
from omni.flux.fcurve.widget import FCurve
from omni.flux.utils.widget import InMemoryGroupedKeysModel

model = InMemoryGroupedKeysModel()
model.commit_payload("curve", curve_to_payload(FCurve(id="curve")))

with ui.Frame():
    editor = CurveEditorWidget(model=model, time_range=(0, 1), value_range=(0, 1))
```

## What It Does

- Visual keyframe and tangent editing (drag, add, delete, copy)
- Tangent types: LINEAR, AUTO, SMOOTH, FLAT, STEP, CUSTOM
- Infinity modes: CONSTANT, LINEAR
- Multi-curve display and editing
- Pluggable grouped-key storage backends
- Single-entry undo hooks for drag-style edits

## Storage Backend

The editor consumes `GroupedKeysModel` from `omni.flux.utils.widget`. Curve UI code converts between `FCurve` objects and suffix-keyed payload dictionaries locally. A curve payload contains `times`, `values`, tangent arrays, and infinity tokens.

USD property-panel persistence is implemented in `omni.flux.property_widget_builder.model.usd`.

## Further Reading

- [Architecture](ARCHITECTURE.md) - component hierarchy, data flow, drag system
