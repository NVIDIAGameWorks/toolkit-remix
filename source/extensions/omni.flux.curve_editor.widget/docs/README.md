# omni.flux.curve_editor.widget

General-purpose bezier curve editor for Omniverse. Edit keyframes, tangent handles, and infinity modes with real-time USD persistence and full undo/redo.

No dependency on `omni.anim`, `omni.timeline`, or OmniGraph.

## Quick Start

```python
from omni.flux.curve_editor.widget import CurveEditorWidget, PrimvarCurveModel

model = PrimvarCurveModel(
    prim_path="/World/MyPrim",
    curve_ids=["opacity:x", "size:x"],
)

with ui.Frame():
    editor = CurveEditorWidget(model=model, time_range=(0, 1), value_range=(0, 1))
```

## What It Does

- Visual keyframe and tangent editing (drag, add, delete, copy)
- Tangent types: LINEAR, AUTO, SMOOTH, FLAT, STEP, CUSTOM
- Infinity modes: CONSTANT, LINEAR
- Multi-curve display and editing
- Pluggable storage backends (USD primvars or in-memory), extendable to write your own backend.
- Single-entry undo for drags, standard undo for toolbar actions

## Storage Backends

| Backend | Use Case |
|---------|----------|
| `PrimvarCurveModel` | USD primvar persistence with Kit command undo/redo |
| `InMemoryCurveModel` | Testing and standalone use |

Implement `CurveModel` to add your own backend.

## Further Reading

- [Architecture](ARCHITECTURE.md) -- component hierarchy, data flow, drag system, primvar format
