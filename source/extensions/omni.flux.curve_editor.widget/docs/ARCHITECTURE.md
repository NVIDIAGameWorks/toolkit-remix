# Curve Editor Architecture

General-purpose curve editor built on `omni.flux.fcurve.widget` with pluggable storage backends.
Decoupled from animation -- no dependency on `omni.anim`, `omni.timeline`, or OmniGraph.

| Component | Role |
|-----------|------|
| **CurveEditorWidget** | Public API. Combines canvas + toolbar. |
| **CurveEditorToolbar** | Tangent type buttons, add/delete key, link/broken toggle. |
| **CurveEditorCanvas** | Hosts FCurveWidget, pan/zoom, grid, rulers. Bridges widget to storage. |
| **FCurveWidget** | MVC model and source of truth for the UI. Owns curve data, handles interaction. |
| **CurveModel** | ABC for pluggable storage. Read, write, change notifications. |
| **PrimvarCurveModel** | USD primvar-backed storage with undo/redo via Kit commands. |
| **InMemoryCurveModel** | Simple dict storage for testing/standalone use. |

## Component Hierarchy

```text
CurveEditorWidget
├── CurveEditorToolbar          (tangent type buttons, add/delete key, link/broken)
└── CurveEditorCanvas           (pan/zoom, grid, rulers, bridges widget ↔ storage)
    ├── FCurveWidget            (MVC model, source of truth, renders curves)
    │   ├── on_commit ─────────────────────────> CurveModel.commit_curve()
    │   ├── on_drag_started ───────────────────> CurveModel.begin_edit()
    │   └── on_drag_ended ─────────────────────> CurveModel.end_edit()
    └── CurveModel.subscribe() <─── Tf.Notice ── PrimvarCurveModel (USD)
                                                  InMemoryCurveModel (testing)
```

## Data Flow

**User action -> Storage (forward)**

```text
User drags key/tangent in FCurveWidget
  -> FCurveWidget updates internal curves
  -> on_commit(curve_id, curve) fires synchronously
  -> CurveEditorCanvas._commit_to_storage -> model.commit_curve
  -> USD primvars written
```

**External change -> UI (reverse)**

```text
Undo / external USD edit
  -> Tf.Notice fires
  -> PrimvarCurveModel._on_usd_objects_changed -> _notify(curve_id)
  -> CurveEditorCanvas._on_model_changed -> _reload_from_storage
  -> FCurveWidget.set_curves(...)
```

## Keyframe/Tangent Dragging Flow

During drags, the system optimizes for real-time feedback and single-entry undo:

1. **Drag start** (first mouse move): FCurveWidget fires `on_drag_started(curve_id)` for all selected curves.
   Canvas calls `model.begin_edit(curve_id)` (model here being PrimvarCurveModel) which snapshots USD state.
2. **During drag** (every frame): `commit_curve` writes directly to USD (no Kit command, no undo entry).
   `PrimvarCurveModel._is_committing` suppresses self-triggered Tf.Notice reloads.
3. **Drag end** (mouse release): FCurveWidget fires `on_drag_ended(curve_id)`.
   Canvas calls `model.end_edit(curve_id)` which creates ONE undoable SetCurvePrimvars command
   with old_values = begin snapshot, new_values = final state.

Simple clicks (select without drag) do NOT trigger begin/end_edit or commit.

## CurveModel Interface

```python
class CurveModel(ABC):
    def get_curve_ids(self) -> list[str]
    def get_curve(self, curve_id: str) -> FCurve | None
    def commit_curve(self, curve_id: str, curve: FCurve) -> None
    def begin_edit(self, curve_id: str) -> None   # continuous edit start
    def end_edit(self, curve_id: str) -> None     # continuous edit end
    def subscribe(self, callback) -> Subscription # external change notifications
```

## Primvar Storage Format

Curves stored as parallel arrays under `primvars:{curve_id}:{property}`:

```usda
def Xform "MyPrim" {
    uniform double[] primvars:opacity:x:times          = [0.0, 0.5, 1.0]
    uniform double[] primvars:opacity:x:values         = [0.0, 1.0, 0.5]
    uniform token[]  primvars:opacity:x:inTangentTypes  = ["linear", "smooth", "linear"]
    uniform token[]  primvars:opacity:x:outTangentTypes = ["linear", "smooth", "linear"]
    uniform double[] primvars:opacity:x:inTangentTimes  = [0.0, -0.25, -0.1]
    uniform double[] primvars:opacity:x:inTangentValues = [0.0, -0.15, 0.0]
    uniform double[] primvars:opacity:x:outTangentTimes = [0.1, 0.25, 0.0]
    uniform double[] primvars:opacity:x:outTangentValues= [0.0, 0.15, 0.0]
    uniform bool[]   primvars:opacity:x:tangentBrokens  = [false, true, false]
    uniform token    primvars:opacity:x:preInfinity     = "constant"
    uniform token    primvars:opacity:x:postInfinity    = "constant"
}
```

Per-channel curves allow independent control (e.g., Vec3 X/Y/Z with different keyframe times).

## File Structure

```text
omni.flux.curve_editor.widget/
├── model/
│   ├── base.py             # CurveModel ABC
│   ├── memory.py           # InMemoryCurveModel
│   ├── primvar.py          # PrimvarCurveModel (USD)
│   └── commands.py         # SetCurvePrimvars command + primvar I/O helpers
├── canvas/
│   ├── main.py             # CurveEditorCanvas
│   ├── grid.py             # GridRenderer
│   ├── rulers.py           # Timeline/Value rulers
│   └── viewport.py         # ViewportState
├── toolbar.py              # CurveEditorToolbar
└── curve_editor_widget.py  # Main public API
```

## Usage

```python
from omni.flux.curve_editor.widget import CurveEditorWidget, PrimvarCurveModel

model = PrimvarCurveModel(prim_path="/World/MyPrim", curve_ids=["opacity:x"])
with ui.Frame():
    widget = CurveEditorWidget(model=model, time_range=(0, 1), value_range=(0, 1))
```
