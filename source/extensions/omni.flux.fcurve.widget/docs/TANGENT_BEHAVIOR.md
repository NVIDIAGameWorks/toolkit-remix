# Tangent Behavior in FCurve Widget

This document describes how tangent types interact to determine curve shape and infinity line directions.

---

## Overarching Design Principles

### Broken Tangent Agnosticism

All logic in this document applies **assuming broken tangents** — meaning the behavior is agnostic of the broken/non-broken state. The matrices and rules work by matching **pairs of in and out tangents** between adjacent keyframes:

- A segment between Key0 and Key1 is defined by: `Key0.outTangent` ↔ `Key1.inTangent`
- Each pair is evaluated independently, without needing to know if a keyframe's tangents are "broken" (independent) or "unbroken" (mirrored/linked).

**Why this works:**
- The interaction matrix only needs to match the relevant tangent pair for each segment.
- Infinity lines only depend on `firstKey.outTangent` (pre-infinity) and `lastKey.inTangent` (post-infinity) — broken state is irrelevant for boundary keyframes.
- All keyframes share the same data structure: **every keyframe has 2 tangents** (in and out), regardless of whether they are broken or linked or boundary keyframes.

### Weighted Tangents: A UX/UI Concept

**Important**: Weighted vs. non-weighted is purely a **UX/UI construct** — it describes whether the user can control the tangent handle's length in the interface.

| Tangent Type | UX Weighted? | User Controls | Internal Reality |
|--------------|--------------|---------------|------------------|
| **LINEAR** | Weighted | Nothing (auto) | Hidden handle at midpoint (computed) |
| **AUTO** | Weighted | Nothing (auto) | Handle position fully computed |
| **SMOOTH** | **Non-weighted** | Angle only | Handle X = halfway to neighbor, Y scaled to preserve angle |
| **FLAT** | Weighted | Nothing (auto) | Handle at neighbor X, keyframe Y |
| **STEP** | N/A | Nothing | No bezier handles (constant segment) |
| **CUSTOM** | **Weighted** | Angle + Length | Handle position as user sets (clamped to neighbor/bbox) |

**Key insight**: From the consumer's perspective (e.g., rendering engine, USD readers), **everything is equally weighted bezier curves**:
- All tangent types compute into full handle positions (X, Y)
- The USD attributes store the **final computed handle positions**
- Consumers process all curves uniformly as bezier math — they don't need to know about "weightedness"

**Example**: SMOOTH mode presents as "non-weighted" in the UI (user only controls angle), but internally we compute and store the hidden handle's full (X, Y) position. The rendering engine sees a normal bezier curve with weighted control points.

This makes the `curve_id:channel:in/outTangentWeighted` USD attribute flags **redundant** — they are not stored in the model because:
1. The weighted flag is fully determined by tangent type (SMOOTH = non-weighted UI, CUSTOM = weighted UI)
2. Consumers don't need it — they receive pre-computed handle positions

---

## Tangent Types Overview

| Type | Description | Handle Position | UX Weighted |
|------|-------------|-----------------|-------------|
| **LINEAR** | Creates straight segments when paired with another LINEAR. Hidden handle placed at midpoint to neighbor. | **Midpoint** to neighboring keyframe | Yes (auto) |
| **AUTO** | Automatically computed smooth tangent based on neighboring keyframes. Only applies to non-boundary keyframes. At boundaries, treated as LINEAR. | Computed from neighbors | Yes (auto) |
| **SMOOTH** | Like AUTO but user can customize the angle. Length is fixed at **halfway** to neighbor (like LINEAR). Y is scaled to preserve the user's angle. | Angle: user-defined, Length: halfway to neighbor | **No** (angle only) |
| **FLAT** | Horizontal tangent (zero slope). Handle extends to neighbor's X position. | X = neighbor's X, Y = keyframe's Y (angle 0°) | Yes (auto) |
| **STEP** | Staircase hold effect (out-tangent only). Segment holds current value, then snaps at next keyframe. Next key's in-tangent is ignored. **STEP as in-tangent falls back to LINEAR.** | N/A (segment is constant + snap) | N/A |
| **CUSTOM** | User-controlled tangent position and angle. Subject to neighbor and bbox clamping (monotonic compliant). | User-defined (clamped) | **Yes** (full control) |

---

## Key Rules

### LINEAR Tangent Behavior

- **LINEAR tangents place a hidden handle at the midpoint** between the keyframe and its neighbor.
- This ensures a **non-zero bezier derivative** at t=0 (or t=1), giving the curve a defined direction at the keyframe.
- When two keyframes share LINEAR tangents between them (`outTangentType = LINEAR` on left key, `inTangentType = LINEAR` on right key), the segment is a **straight line** because both hidden handles lie on the line connecting the keyframes.
- For bezier computation: P1 (first control point) is at the midpoint between P0 (keyframe) and the neighboring keyframe.

```text
LINEAR out-tangent example:

Key0 -------- [hidden handle at midpoint] -------- Key1
 P0                      P1                         P3
```

### AUTO Tangent Behavior

- **AUTO only applies to non-boundary keyframes** (keyframes that have neighbors on both sides).
- The AUTO algorithm uses the **two neighboring keyframes** to compute:
  1. **Tangent angle**: Derived from the positions of the left and right neighbors.
  2. **Tangent length (X)**: Clamped so the handle doesn't exceed the adjacent keyframe's position, preventing curve overlap/multiple Y values.

### AUTO + AUTO Between Two Keyframes

When two adjacent keyframes both have AUTO tangents facing each other:
- `left.outTangentType = AUTO`
- `right.inTangentType = AUTO`

**Handle X Position**: Both tangent handles meet at the **midpoint** between the two keyframes (in X).

**Angle Computation**:
- **Left key's out-tangent angle**: Computed from `left's left neighbor` → `right keyframe` direction.
- **Right key's in-tangent angle**: Computed from `left keyframe` → `right's right neighbor` direction.

### SMOOTH Tangent Behavior

- **SMOOTH is like AUTO**, but the **angle can be customized** by the user.
- The user can freely position the handles for UX convenience, but **length is fixed** (non-weighted UX).
- **Handle X = halfway to neighbor** — the same as LINEAR's midpoint approach, creating a natural circular arc shape.
- **Handle Y is scaled** to preserve the user's angle at this fixed X position.
- This creates a **constant-length tangent** that follows a predictable circular trajectory when dragged, rather than the awkward behavior of extending all the way to the neighbor.
- **UX non-weighted, internally weighted**: The user controls only angle, but the computed handle position is stored and processed as a normal weighted bezier control point.

```text
SMOOTH out-tangent example:

Key0 ──────────● [handle at HALFWAY to Key1, Y scaled for angle] ────────────── Key1
              ↑
         X = (Key1.time - Key0.time) / 2
         Y = user_angle_y * scale
```

**Why halfway distance (not full)**:
- Creates a **circular arc** trajectory when dragging the handle
- Matches LINEAR's midpoint behavior for consistency
- Avoids extreme Y positions that occur when extending to full neighbor distance
- More intuitive UX — handle stays in a predictable zone

#### SMOOTH with Vertical Angle (X=0)

When the user sets or drags a SMOOTH tangent to a vertical angle (X=0):
- **The vertical tangent is preserved** — X stays at 0, Y is preserved (clamped to bbox if needed).
- SMOOTH does **NOT** fall back to horizontal when X=0.
- This allows users to intentionally create vertical tangents with SMOOTH type.

**Why this design**: If the user explicitly drags to vertical, they want vertical. Resetting to horizontal would be counter-intuitive and lose user intent.

### CUSTOM Tangent Behavior

- **CUSTOM tangents offer user-controlled positioning** — the user can freely adjust handles in both X and Y.
- **UX weighted and internally weighted**: Both angle and length are user-defined — what you set is what gets stored and rendered (after clamping).
- **Monotonic curve compliant**: CUSTOM handles are subject to the same clamping rules as other tangent types:
  1. **Y-axis flip prevention**: IN tangent X ≤ 0, OUT tangent X ≥ 0.
  2. **Neighbor keyframe clamping**: Handle X cannot extend beyond the neighboring keyframe's X position.
  3. **Bounding box clamping**: Handles must stay within the curve's X-Y range.
- **Ray-box intersection preserves angle**: When clamping is applied, both X and Y are scaled proportionally to preserve the user's intended angle while staying within bounds.
- This is the only tangent type where the user's handle position directly maps to the stored bezier control point (after clamping).

**Key difference from other auto-computed types**:
- **OTHER types** (LINEAR, AUTO, SMOOTH, FLAT): Some form of auto-computation determines handle position.
- **CUSTOM**: No auto-computation — raw user values are preserved, only clamping is applied.

### FLAT Tangent Behavior

- **FLAT tangents are horizontal** — the Y derivative/angle is always **0°**.
- The handle's **X position equals the neighboring keyframe's X position** (full extension).
- This creates a smooth horizontal approach/departure at the keyframe.

```text
FLAT out-tangent example:

Key0 ════════════════════════════ [handle at neighbor X, same Y as Key0] ──── Key1
         horizontal (angle = 0°)
```

**Use case**: When you want the curve to arrive at or depart from a keyframe with zero slope (no acceleration/deceleration in Y).

### STEP Tangent Behavior

**Industry Standard**: STEP is an **out-tangent property** that governs the departing segment. This follows the convention used in Maya, Blender, and other DCCs.

#### STEP as Out-Tangent (Valid)

When a keyframe has `outTangentType = STEP`:
- The segment from this keyframe to the next is **constant** at this keyframe's value.
- The **next keyframe's in-tangent is ignored** — STEP fully defines the segment behavior.
- The value **snaps** to the next keyframe's value exactly at the next keyframe's X position.

```text
STEP out-tangent example (Key0 has out=STEP):

Key0 ════════════════════════════════════════╗
     [constant at Key0's Y value]            ║ ← snap at Key1's X
                                             ╚════ Key1
```

#### STEP as In-Tangent (Falls Back to LINEAR)

**STEP as an in-tangent does not make sense** in the industry-standard model — the out-tangent of the previous key controls the segment shape, not the in-tangent of the receiving key.

When a keyframe has `inTangentType = STEP`:
- **Treat as LINEAR** — place a hidden handle at the midpoint to the previous keyframe.
- The segment uses normal bezier interpolation (governed by the previous key's out-tangent).
- This provides consistent, predictable fallback behavior.

**Why this design**:
- DCCs like Maya define stepped interpolation on the *source* keyframe's out-tangent.
- The out-tangent says "how the curve leaves this keyframe" — STEP means "hold my value until the next key."
- The in-tangent says "how the curve arrives at this keyframe" — but by the time we arrive, the segment is already defined by the previous key's out-tangent.

**Use case**: Sample-and-hold effects, discrete value changes, animation holds.

### Why Bezier Derivatives

We rely on **bezier derivatives and math** for curve computation because they are stable given the multitude of situations a keyframe might be in relation to its neighbors. Whether a keyframe has LINEAR, AUTO, SMOOTH, or CUSTOM tangents — and regardless of what its neighbors have — the bezier math consistently produces the correct curve shape and direction at any point.

### STEP and FLAT at Boundaries (Infinity)

- **STEP tangent** at a boundary: For infinity computation, treat as **CONSTANT infinity type** (horizontal line at the keyframe value).
- **FLAT tangent** at a boundary: Same as STEP — treat as **CONSTANT infinity type** since the intent was a horizontal/straight line.

---

## Tangent Interaction Matrix

### Between Two Adjacent Keyframes (Left → Right)

| Left Out-Tangent | Right In-Tangent | Segment Behavior |
|------------------|------------------|------------------|
| LINEAR | LINEAR | **Straight line** — both hidden handles on the line at midpoints |
| LINEAR | AUTO | Left handle at midpoint, right's AUTO computed from neighbors |
| AUTO | LINEAR | Left's AUTO computed from neighbors, right handle at midpoint |
| AUTO | AUTO | Both compute smooth angles, handles meet at midpoint |
| CUSTOM | AUTO | Right's AUTO computed, left uses user-defined handle |
| AUTO | CUSTOM | Left's AUTO computed, right uses user-defined handle |
| FLAT | FLAT | **Horizontal S-curve** — both handles horizontal, meeting at segment center |
| FLAT | LINEAR | Left horizontal to midpoint, right at midpoint (smooth horizontal start) |
| LINEAR | FLAT | Left at midpoint, right horizontal from midpoint (smooth horizontal end) |
| STEP | *any* | **Constant + snap** — right's in-tangent ignored, holds left Y, snaps at right |
| *any* | STEP | Right's STEP treated as LINEAR — normal bezier using left's out-tangent |

---

## Infinity Line Angle Computation

The infinity lines (extrapolation before first key and after last key) derive their angles from the boundary keyframes' tangents.

### Key Rule: Which Tangent Matters

| Infinity | Depends On | Why |
|----------|------------|-----|
| **Pre-infinity** (before first key) | First keyframe's **out-tangent** only | The out-tangent defines the curve direction leaving the first key |
| **Post-infinity** (after last key) | Last keyframe's **in-tangent** only | The in-tangent defines the curve direction arriving at the last key |

### Pre-Infinity (Before First Keyframe)

Use the **bezier derivative at t=0** of the first segment to compute the angle. This works for all tangent types:
- **LINEAR**: Derivative points toward the midpoint handle → toward the next keyframe.
- **AUTO/SMOOTH/CUSTOM**: Derivative points along the out-tangent direction.
- **FLAT**: Derivative is horizontal (0° angle) → treat as CONSTANT infinity.
- **STEP**: Treat as CONSTANT infinity.

### Post-Infinity (After Last Keyframe)

Use the **bezier derivative at t=1** of the last segment to compute the angle. This works for all tangent types:
- **LINEAR**: Derivative points from the midpoint handle → from the previous keyframe direction.
- **AUTO/SMOOTH/CUSTOM**: Derivative points along the in-tangent direction.
- **FLAT**: Derivative is horizontal (0° angle) → treat as CONSTANT infinity.
- **STEP**: Treat as CONSTANT infinity.

### Unified Approach: Bezier Derivatives

Since all tangent types (including LINEAR) now produce non-zero control points, the bezier derivative is the **universal method** for computing infinity line angles:
- **t=0 derivative**: Direction from P0 → P1 (keyframe → first control point)
- **t=1 derivative**: Direction from P2 → P3 (last control point → keyframe)

This is exactly what the renderer's `start_tangent_width/height` and `end_tangent_width/height` represent.

---

## Boundary Keyframe Considerations

### First Keyframe (No Left Neighbor)

- **AUTO tangent** cannot fully apply (no left neighbor for angle computation).
- **Treat AUTO as LINEAR** at boundary keyframes — the hidden handle is placed at the midpoint to the next keyframe.
- This gives a well-defined direction for the pre-infinity line (pointing toward the second keyframe).

### Last Keyframe (No Right Neighbor)

- **AUTO tangent** cannot fully apply (no right neighbor for angle computation).
- **Treat AUTO as LINEAR** at boundary keyframes — the hidden handle is placed at the midpoint from the previous keyframe.
- This gives a well-defined direction for the post-infinity line (continuing from the second-to-last keyframe).

---

## Visual Examples

### Case 1: All LINEAR

```text
Key0 (LINEAR) -------- Key1 (LINEAR) -------- Key2 (LINEAR)
        [straight]              [straight]
```

### Case 2: First LINEAR, Middle AUTO, Last LINEAR

```text
Key0 (out=LINEAR) ~~~~ Key1 (in=AUTO, out=AUTO) ~~~~ Key2 (in=LINEAR)
     [midpoint]              [smooth]           [midpoint]
```

- Key0's out-tangent handle is at midpoint toward Key1.
- Key1's AUTO tangents are computed from Key0 and Key2 positions.
- Key2's in-tangent handle is at midpoint from Key1.
- The curve smoothly transitions through Key1.
- Key0's pre infinity line will have the same angle as key0's out-tangent angle, flipped.
- Key2's post infinity line will have the same angle as key2's in-tangent angle, flipped.

### Case 3: All AUTO

```text
Key0 (out=AUTO*) ~~ Key1 (in=AUTO, out=AUTO) ~~ Key2 (in=AUTO*)
    [midpoint]           [smooth]          [midpoint]
```

*Note: Boundary keys (Key0, Key2) have AUTO treated as LINEAR — hidden handles at midpoint to neighbor.

### Case 4: STEP (Staircase Hold)

```text
Key0 (out=STEP)       Key1 (out=STEP)
    ╔═════════════════════╗
    ║                     ║
════╝                     ╚════════════ Key2
[hold Key0 Y]  [snap]  [hold Key1 Y]  [snap]
```

- Segment Key0→Key1: Key0's out=STEP holds at Key0's Y value, snaps to Key1's Y at Key1's X position.
- Segment Key1→Key2: Key1's out=STEP holds at Key1's Y value, snaps to Key2's Y at Key2's X position.
- Key1's in-tangent is ignored (Key0's out=STEP overrides the segment).
- Key2's in-tangent is ignored (Key1's out=STEP overrides the segment).

**Note**: STEP is defined on the **out-tangent** of the source keyframe. If a key has `in=STEP`, it falls back to LINEAR behavior.

### Case 5: FLAT (Horizontal Tangents)

```text
Key0 ════════════════╗
                      ╲
                       ╲  [smooth S-curve]
                        ╲
                         ╚════════════════ Key1
```

- Both Key0 (out=FLAT) and Key1 (in=FLAT) have horizontal tangents.
- The curve smoothly transitions with zero slope at both endpoints.
- Handles extend to meet at the segment's center horizontally.

### Case 6: Mixed FLAT and LINEAR

```text
Key0 ════════════════────────────── Key1
        [horizontal]    [straight to midpoint]
```

- Key0 (out=FLAT): Horizontal departure.
- Key1 (in=LINEAR): Midpoint handle creates a smooth but asymmetric curve.

---

## Implementation Notes

### During Keyframe Drag

When a keyframe is moved:
1. All affected AUTO tangents must be **recomputed** based on new positions.
2. Bezier segments are rebuilt with updated control points.
3. Infinity lines must update their angles from the **rendered bezier segment tangents** (not from stale model data).

### Data Flow for Keyframe/Tangent Updates

```text
Keyframe or tangent handle moved (user interaction)
    ↓
Tangents recomputed (AUTO/LINEAR midpoints recalculated)
    ↓
Final clamping pass applied (X and Y bounds enforced)
    ↓
Model updated with final computed values
    ├─ key.time, key.value
    ├─ in_tangent (clamped/computed position)
    └─ out_tangent (clamped/computed position)
    ↓
Bezier segments rebuilt with new control points
    ↓
Infinity renderer computes angles from bezier derivatives:
    ├─ Pre-infinity angle: bezier derivative at t=0 of first segment
    └─ Post-infinity angle: bezier derivative at t=1 of last segment
    ↓
UI rendered with correct curves and infinity lines
```

**Important**: The model must always be updated with the final computed/clamped values. This ensures model and rendered handles stay in sync. If the model stored raw user input while the renderer used clamped values, they would diverge.

The bezier derivative at the endpoints equals `start_tangent_width/height` and `end_tangent_width/height` from the rendered segments. This unified approach works for all tangent types since all (including LINEAR) produce non-zero control points.

---

## Handle Clamping

**Universal Rule: All handles in all tangent types must be clamped to the curve's X-Y range** — no handle should go outside the curve's bounding box. This applies to both X and Y positions, in all situations.

### Y-Axis Flip Prevention (HARD Rules)

Tangent handles must never "flip" past the keyframe's Y-axis:
- **IN tangent X must be ≤ 0** — points left or vertical (toward previous keyframe).
- **OUT tangent X must be ≥ 0** — points right or vertical (toward next keyframe).

When the user drags a tangent past the Y-axis:
1. **X is clamped to 0** (vertical) — the tangent cannot flip to point the wrong direction.
2. **Y is preserved** from the drag position (clamped to bbox if needed).
3. For SMOOTH tangents, this results in a vertical tangent with the user's Y value preserved.

**Why this design**: Flipping tangents past the Y-axis would cause bezier curves to loop back on themselves, creating invalid curves with multiple Y values for a single X. The Y-axis is a hard boundary that tangents cannot cross.

### Curve Range Definition

The **curve X-Y range** is defined by the **viewport settings** — the same setting that controls the curve's allowed value range. This makes the clamping behavior consistent with the viewport constraints and provides a clean consumer API.

### Clamping Rules by Tangent Type

| Tangent Type | X Clamping | Y Clamping |
|--------------|------------|------------|
| **LINEAR** | Handle X = midpoint to neighboring keyframe (fixed) | Midpoint Y (on line to neighbor) |
| **AUTO** | Handle X ≤ neighboring keyframe's X position | Within curve Y range |
| **SMOOTH** | Handle X = halfway to neighbor (like LINEAR), or X=0 if vertical | Within curve Y range |
| **FLAT** | Handle X = neighboring keyframe's X (fixed) | Y = keyframe's Y (horizontal, fixed) |
| **STEP** | N/A (no bezier handles) | N/A (constant segment + snap) |
| **CUSTOM** | Handle X ≤ neighboring keyframe's X position | Within curve Y range |

**Note**: All tangent types are also subject to **Y-axis flip prevention** — IN tangent X ≤ 0, OUT tangent X ≥ 0.

### Why CUSTOM Uses Neighbor Clamping

CUSTOM tangents are clamped to the neighboring keyframe's X position (not just the curve bounds) to ensure **monotonic curve compliance**:
- Prevents bezier curves from looping back on themselves.
- Ensures each X coordinate maps to exactly one Y value.
- Makes CUSTOM curves compatible with time-based interpolation (no backward time travel).
- Preserves the user's intended angle via ray-box intersection when clamping occurs.

### X Clamping in AUTO Mode

In AUTO mode, the **neighboring keyframe's X position** defines the maximum X position for the tangent handle, regardless of the neighbor's tangent type:
- If left key has `outTangentType = AUTO` and right key has any type (even CUSTOM), the left key's out-handle X is clamped to not exceed the right key's X position.
- This prevents curve overlap and ensures monotonic X progression.

### Implementation: Final Clamping Pass

A **final clamping pass** should be applied after all tangent computations:
1. Compute tangent angles and lengths based on type rules.
2. Apply X clamping based on neighboring keyframes.
3. Apply Y clamping based on curve range.
4. Rebuild bezier segments with clamped values.

### UX: Out-of-Bounds Handle Feedback

When the user drags a tangent handle outside the curve's X-Y range:

**During drag:**
1. **Clamped handle** (half opacity): Render the handle at the computed clamped position with 50% opacity.
2. **Out-of-bounds indicator** (red line at 50% opacity): Draw a red line (`0x800000FF` - ABGR) extending from the clamped handle position to the actual dragged position.

**On mouse release:**
- The dragged position **snaps** to the clamped position.
- The red indicator line and ghost handle disappear.
- The handle is now at the clamped position at full opacity.

This visual feedback communicates to the user that:
- The dragged position is out of bounds.
- The actual handle position used for computation is the clamped one.
- On release, the handle will snap to the valid clamped position.
