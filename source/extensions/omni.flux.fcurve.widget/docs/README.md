# omni.flux.fcurve.widget

Reusable bezier curve widget for rendering and editing function curves.
Decoupled from any storage mechanism -- bring your own persistence via callbacks.

## Quick Start

```python
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

- Multiple bezier curves with independent colors
- Keyframe drag, add, delete, multi-select
- Tangent handle editing: LINEAR, AUTO, SMOOTH, FLAT, STEP, CUSTOM
- Linked/broken tangent modes
- Pre/post infinity extrapolation (CONSTANT, LINEAR)
- `on_commit` callback for synchronous storage persistence
- `on_drag_started` / `on_drag_ended` callbacks for undo batching

## Further Reading

- [Architecture](ARCHITECTURE.md) -- tangent pipeline, layer constraints, data flow
- [Tangent Behavior](TANGENT_BEHAVIOR.md) -- tangent type rules, clamping, interaction matrix
