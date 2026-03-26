# FCurve Architecture: Tangent Pipeline

## Overview

This document defines the architecture for FCurve tangent and keyframe handling.

### TL;DR
- **UIManager**: Manages keyframe/tangent widgets, events, and pixel↔model conversion.
- **process_curve**: Single entry point that builds KeyframeGestureData and calls process_keyframes.
- **Model (FCurve.keys)**: Source of truth. Mutated in place. No return value — model is the result.

---

## Architecture After Refactor

```text
UIManager (events, pixel↔model)
    └── process_curve(curve, bounds, threshold, key_positions, tangent_positions)
            └── builds KeyframeGestureData, calls process_keyframes()
                    └── mutates curve.keys in place
```

- **Model** = source of truth (FCurve.keys). Mutated in place.
- **UI** = reads from model after process. Ghost lines: model position vs raw widget position when they differ.
- **No return value** — model is the result.

---

## Core Principles

1. **Model is the source of truth.** All tangent and keyframe data lives in FCurve.keys. process_curve mutates keys in place.

2. **Model space everywhere.** All layers work in model coordinates (time, value as floats). Only UIManager knows about pixels/screen positions.

3. **Single pipeline.** process_keyframes (via process_curve) handles all tangent type computation, mirroring, and bounds clamping.

## Tangent Type Computation (process_keyframes)

process_keyframes computes tangent positions based on tangent TYPE:
- **LINEAR**: Points directly at neighbor keyframe (midpoint)
- **FLAT**: Horizontal tangent (Y offset = 0)
- **STEP**: Instant value change (no interpolation)
- **AUTO**: Uses Catmull-Rom to compute angle based on neighbors
- **SMOOTH**: User controls angle, length == half distance to neighbor keyframe
- **CUSTOM**: User-defined values, no automatic computation

See TANGENT_BEHAVIOR.md for full specification.

## Ghost Line Feedback

Ghost line feedback is shown when the user is dragging and the model position differs from the raw widget position.

```text
During drag:
  if raw_ui_drag_position != model_position:
    show a ghost marker at model position
    show line from model to raw_ui_drag_position

On release:
  model is already updated by process_curve
  widget reads from model
```

## Key Constraints

| Component | Responsibility |
|-----------|----------------|
| UIManager | Events, pixel↔model, widget creation, calls process_curve |
| process_curve | Builds KeyframeGestureData from overrides, calls process_keyframes |
| process_keyframes | Mutates curve.keys in place (tangent types, mirroring, clamping) |
| Model (FCurve.keys) | Single source of truth |
