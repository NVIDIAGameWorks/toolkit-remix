# Curve Editor Architecture

General-purpose curve editor built on `omni.flux.fcurve.widget` with a pluggable grouped-key storage backend. The editor is decoupled from animation systems and from USD.

| Component | Role |
|-----------|------|
| **CurveEditorWidget** | Public widget that combines canvas and toolbar. |
| **CurveEditorToolbar** | Tangent type buttons, add/delete key, link/broken toggle. |
| **CurveEditorCanvas** | Hosts `FCurveWidget`, pan/zoom, grid, rulers, and bridges UI events to storage. |
| **FCurveWidget** | In-memory UI source of truth for rendered curves and interactions. |
| **GroupedKeysModel** | Shared storage contract for curve and gradient grouped-key payloads. |
| **InMemoryGroupedKeysModel** | Simple dict storage for testing and standalone use. |

## Component Hierarchy

```text
CurveEditorWidget
|-- CurveEditorToolbar          (tangent type buttons, add/delete key, link/broken)
`-- CurveEditorCanvas           (pan/zoom, grid, rulers, bridges widget <-> storage)
    |-- FCurveWidget            (MVC model, source of truth, renders curves)
    |   |-- on_commit ---------> GroupedKeysModel.commit_payload()
    |   |-- on_drag_started ---> GroupedKeysModel.begin_edit()
    |   `-- on_drag_ended -----> GroupedKeysModel.end_edit()
    `-- GroupedKeysModel.subscribe() receives external storage changes
```

## Data Flow

**User action to storage**

```text
User edits a key or tangent in FCurveWidget
  -> FCurveWidget updates internal curves
  -> on_commit(curve_id, curve) fires synchronously
  -> CurveEditorCanvas converts FCurve to a grouped payload
  -> model.commit_payload(curve_id, payload)
```

**External change to UI**

```text
Undo or external storage edit
  -> backend notifies GroupedKeysModel subscribers
  -> CurveEditorCanvas reloads payloads from storage
  -> payloads are converted to FCurve objects
  -> FCurveWidget.set_curves(...)
```

## Drag Flow

During drags, the system optimizes for real-time feedback and single-entry backend undo:

1. Drag start: `FCurveWidget` fires `on_drag_started(curve_id)` for selected curves, and the canvas calls `model.begin_edit(curve_id)`.
2. During drag: each preview value is sent through `model.commit_payload(curve_id, payload)`.
3. Drag end: `FCurveWidget` fires `on_drag_ended(curve_id)`, and the canvas calls `model.end_edit(curve_id)`.

Simple selection clicks do not trigger `begin_edit`, `commit_payload`, or `end_edit`.

## GroupedKeysModel Interface

```python
class GroupedKeysModel(ABC):
    @property
    def group_ids(self) -> list[str]
    def get_payload(self, group_id: str) -> dict[str, Any] | None
    def commit_payload(self, group_id: str, payload: dict[str, Any]) -> None
    def begin_edit(self, group_id: str) -> None
    def end_edit(self, group_id: str) -> None
    def subscribe(self, callback: Callable[[str], None]) -> EventSubscription
    def get_display_name(self, group_id: str) -> str
    def destroy(self) -> None
```

Curve payload conversion helpers live in `omni.flux.curve_editor.widget.payload`. USD primvar storage for property panels lives in `omni.flux.property_widget_builder.model.usd`.

## File Structure

```text
omni.flux.curve_editor.widget/
|-- payload.py                 # FCurve <-> grouped payload conversion
|-- canvas/
|   |-- main.py                # CurveEditorCanvas
|   |-- grid.py                # GridRenderer
|   |-- rulers.py              # Timeline/Value rulers
|   `-- viewport.py            # ViewportState
|-- toolbar.py                 # CurveEditorToolbar
`-- curve_editor_widget.py     # Main public widget
```
