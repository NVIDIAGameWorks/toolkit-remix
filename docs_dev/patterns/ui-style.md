# Building UI Components

Tips for creating well-structured UIs using `omni.ui`.

**Reference
**: [Omniverse UI Framework](http://omniverse-docs.s3-website-us-east-1.amazonaws.com/omni.ui/2.25.9/Overview.html)

---

## General Guidelines

### Follow existing UI style

When adding a new feature, find the nearest existing similar feature and use it as a baseline.

- If you add a list with checkboxes, checkboxes appear at the start of every row.
- If you add a list, wrap it in a `ScrollingFrame` so it can grow without forcing a window resize.

### Post mockups and progress for review

Post a mockup to the tools channel early — it's far easier to iterate in paint than in code. Post progress screenshots
as you go to get ideas before UIs are final. When giving feedback, note whether something is a preference or an actual
UX problem.

### Check alignment

All UI elements should align pixel-perfectly. Use screenshots and draw guidelines in Paint to verify.

**Common alignment problems to catch before review:**

- Elements that appear visually close but are not pixel-aligned (e.g. a label and an input field that look paired but
  have different top edges)
- Column edges or adjacent elements that are different lengths — every column in a list or form should terminate at the
  same horizontal line
- Missing left padding on the first column — the leftmost element in a list or form should have the same inset as
  everything else
- Scrollbars that are always visible — a scrollbar should only appear when content exceeds available space, and its
  width should exactly match the width of the tree or list it scrolls

### Use consistent values for similar UI elements

Use named constants (e.g. `self._DEFAULT_WIDGET_HEIGHT = 300`) to share values across aligned widgets. Reuse the same
padding in adjacent widgets to communicate visual grouping.

### Property input tooltips identify fields

Shared USD property value tooltips should identify the field being edited as well as the current value. Scalar fields use
`<Display Name>: <value>`, and generic vector fields use `<Display Name> <channel>: <value>` with channels derived from
the value type as `X`, `Y`, `Z`, and `W`. Color value types are treated as single color-widget values rather than
generic vector channels. Label tooltips remain reserved for schema/help documentation.

### Avoid hardcoded dimensions

`ui.Pixel(293)` is almost never necessary. Build layouts by setting sizes to 0 or leaving them unset:

| Value         | Meaning                                                           |
|---------------|-------------------------------------------------------------------|
| `0`           | Use as little space as possible                                   |
| `ui.Pixel(n)` | Always use exactly `n` pixels (good for icons, column widths)     |
| unset         | Use all available space; multiple unset items share space equally |

### Use `omni.ui` dimension objects, not raw floats

Use `ui.Pixel(16)` instead of `16`. `ui.Pixel` values scale with DPI; raw floats do not. The only exception is `0`,
which is always zero regardless of DPI.

**Never pass raw integers to `spacing`, `width`, or `height`** — always wrap in `ui.Pixel(...)`:

```python
# Correct
ui.HStack(spacing=ui.Pixel(8))
ui.Spacer(width=ui.Pixel(12))

# Wrong — raw int, won't scale with DPI
ui.HStack(spacing=8)
ui.Spacer(width=12)
```

**Never use magic numbers** — define all dimensions as class or module-level constants using `ui.Pixel`:

```python
# Correct — constant IS a ui.Pixel, used directly
_HEADER_PADDING = ui.Pixel(12)
_ICON_SIZE = ui.Pixel(16)
ui.Spacer(width=_HEADER_PADDING)
ui.Image("", width=_ICON_SIZE, height=_ICON_SIZE)

# Wrong — raw int constant wrapped at usage site
_HEADER_PADDING = 12
ui.Spacer(width=ui.Pixel(_HEADER_PADDING))

# Wrong — magic numbers inline
ui.Spacer(width=ui.Pixel(12))
```

### Think in spacing, not dimensions

Use the `spacing` kwarg on stacks to add consistent gaps between children rather than sizing individual items.

### Adding padding to a window

Wrap your layout in an `HStack` and `VStack` with `spacing` set, and add zero-size spacers at the edges:

```python
with ui.HStack(spacing=ui.Pixel(16)):
    ui.Spacer(width=0, height=0)
    with ui.VStack(spacing=ui.Pixel(16)):
        ui.Spacer(width=0, height=0)
        # your widget here
        ui.Spacer(width=0, height=0)
    ui.Spacer(width=0, height=0)
```

### Layout constants — define at class or module level

All `ui.Pixel` sizes, spacing values, and dimension constants must be defined at the **class level** (or module
level for delegates), never inline. Use descriptive names.

```python
# Good — class-level constants
class MyWidget:
    _SPACING_SMALL = ui.Pixel(4)
    _SPACING_MEDIUM = ui.Pixel(16)
    _INPUT_NAME_WIDTH = ui.Pixel(90)
    _ROW_HEIGHT = ui.Pixel(26)
    _HOST_WIDTH = ui.Fraction(1)

# Bad — inline magic numbers
ui.HStack(spacing=ui.Pixel(16))
ui.Label(width=90)
ui.Spacer(height=8)
```

Follow the pattern from `ComfySetupAdvancedWidget` (`_SPACING_SM`, `_PROTOCOL_WIDTH`, `_ICON_SIZE`) and
`JobQueueDetailsPanel` (`_HEADER_PADDING`, `_HEADER_HEIGHT`, `_CELL_PADDING`).

### Layout spacing — no inline style dicts

Never use `style={"margin": ...}` or inline `style={}` dicts on `omni.ui` widgets. All padding and spacing
must use explicit layout primitives:

- `VStack`/`HStack` with `spacing=` argument for consistent gaps between children
- `ui.Spacer(width=X)` / `ui.Spacer(height=X)` for padding at container edges

```python
# Good — explicit spacer-based padding
with ui.VStack(spacing=_SECTION_SPACING):
    ui.Spacer(height=_CONTENT_PADDING)
    with ui.HStack():
        ui.Spacer(width=_CONTENT_PADDING)
        # content
        ui.Spacer(width=_CONTENT_PADDING)
    ui.Spacer(height=_CONTENT_PADDING)

# Bad — inline style dict
with ui.VStack(style={"margin": 5}):
    # content
```

---

## Remix-Specific Guidelines

### Use `trex.app.style` for stylesheet changes

Don't add styles directly to widgets. Route all stylesheet changes through `trex.app.style`.

### Use existing icons for existing concepts

Don't introduce new icons when an existing one fits. When you do need new icons:

1. Prefer [MDI icons](https://pictogrammers.com/library/mdi/)

### Avoid introducing new colors

Don't add new color values to the stylesheet unless there is no existing color that fits.

### Keep style names generic

If a style could reasonably apply to more than one widget, don't include the specific widget name in the style key. Only
scope a style name to a specific widget if it must not affect anything else.

> Note: many existing styles don't follow this rule — that's a known problem, not a model to copy.

---

## Tree Widget Patterns (Stage Manager Reference)

When building tree-based UIs, use the Stage Manager (`omni.flux.stage_manager`) as the canonical reference. The
patterns below were validated against the Stage Manager implementation and represent the required approach for any new
tree widget in this codebase.

### 1. Layout Structure for Tree Widgets

The correct layer order from outermost to innermost:

```text
ZStack
+-- Rectangle(name="WorkspaceBackground")   <- opaque GREY_50 background
+-- VStack
    +-- toolbar
    +-- VStack  (inner content)
        +-- ZStack
        |   +-- ScrollingTreeWidget  (tree)
        |   +-- separators           (ui.Frame with separate_window=True)
        |   +-- empty-state overlay  (opaque Rectangle + message)
        +-- footer                   <- OUTSIDE the ZStack
```

Use `Rectangle(name="WorkspaceBackground")` backed by an opaque `GREY_50` color as the base background. Do NOT use
`TreePanelBackground` for this purpose — its style has `background_color: 0x0` (fully transparent), which renders as
black on a dark window chrome.

The Stage Manager widget (`omni.flux.stage_manager.widget/widget.py:103`) uses `Rectangle(name="TabBackground")`
(`GREY_42`) as its outermost background. Use whichever grey token matches the surrounding panel depth.

The footer must sit **outside** the `ZStack` that holds the tree and separators. If the footer is inside the `ZStack`,
separator lines will extend visually through the results bar.

### 2. ScrollingTreeWidget Background

`ScrollingTreeWidget._build_ui()` creates a `ScrollingFrame(name="TreePanelBackground")` internally. The style for
`ScrollingFrame::TreePanelBackground` sets `background_color: 0x0`, making the frame fully transparent.

The grey background visible in the tree area does not come from the tree widget itself — it comes from the opaque
`Rectangle` placed behind it in the parent `ZStack`. Never try to fix a "black tree" by patching
`ScrollingTreeWidget`; instead, check that the background `Rectangle` is present and correctly styled.

### 3. Cell Height — `ui.Frame` Wrapping in Delegates

Every `_build_widget` and `_build_header` call in a tree delegate must be wrapped in an explicit `ui.Frame` with a
fixed height:

```python
# Stage Manager reference: tree_plugin.py:538
def _build_widget(self, model, item, column_id, level, expanded):
    with ui.Frame(height=self.row_height):
        # cell content here

# Stage Manager reference: tree_plugin.py:547
def _build_header(self, column_id):
    with ui.Frame(height=self.header_height):
        # header content here
```

Without this wrapper, cell content can collapse to zero height. The `TreeView` still allocates the row and renders
selection highlights for it, but the delegate content is invisible — producing "ghost rows" where selections appear on
seemingly empty rows.

### 4. Consistent Spacing — HorizontalColumn Pattern

Use `HStack` with a `spacing` attribute and zero-size `Spacer` sentinels at both ends to create equal padding on all
sides:

```python
# Reference: omni.flux.stage_manager.plugin.column/horizontal_column.py:29
_HORIZONTAL_PADDING = 8

with ui.HStack(spacing=ui.Pixel(_HORIZONTAL_PADDING)):
    ui.Spacer(width=0, height=0)
    # column content
    ui.Spacer(width=0, height=0)
```

Define all padding values as module-level constants — never use magic numbers inline.

| Constant | Value | Used for |
|---|---|---|
| `_RESULTS_HORIZONTAL_PADDING` | `8` | Scrollbar region inset |
| `_RESULTS_VERTICAL_PADDING` | `4` | Footer padding |
| `_FILTERS_VERTICAL_PADDING` | `8` | Filter row padding |

### 5. Column Separators

Place separators inside the `ZStack` that contains the tree, not inside the footer. Use `ui.Frame(separate_window=True)`
as the container so separators render above the tree content:

```python
# Reference: interaction_plugin.py:404-413
with ui.Frame(separate_window=True):
    with ui.HStack():
        for i, column in enumerate(columns):
            if i == 0:
                continue  # skip drag-handle column
            ui.Separator(width=1)
            # remaining column widths
```

Skip the separator for index `0` when the first column is a drag handle — adding a leading separator there creates an
unintended border at the left edge.

### 6. WorkspaceWidget Interface

`WorkspaceWindowBase._update_ui()` calls `self._content.show(True)` on the widget returned by `_create_window_ui()`.
Any widget returned from that method must implement a `show(visible: bool)` method.

The Stage Manager achieves this via a mixin (`StageManagerWidget(_StageManagerWidget, _WorkspaceWidget)`). However,
`ui.Frame` uses a C++ metaclass (pybind11) that is incompatible with `abc.ABCMeta`. Multiple inheritance between a
`ui.Frame` subclass and a class backed by `ABCMeta` raises:

```
TypeError: metaclass conflict: the metaclass of a derived class must be a
(non-strict) subclass of the metaclasses of all its bases
```

The correct fix is to add `show()` directly to the `ui.Frame` subclass as a concrete method, not via mixin:

```python
class MyTreeWidget(ui.Frame):
    def show(self, visible: bool) -> None:
        self.visible = visible
```

### 7. AlternatingRowWidget Ghost Item Trap

`ScrollingTreeWidget` with `alternating_rows=True` creates an internal `AlternatingRowWidget` background layer. This
layer always renders `max(item_count, min_row_count)` rows to fill the visible area — even when the model is empty.

When the foreground tree is empty, click events fall through to the alternating-row `TreeView` and can select a
background row, producing unexpected selection state with no visible item.

Fix: ensure the empty-state overlay (an opaque `Rectangle` plus a message label) fully covers the tree area whenever
the model is empty. Call `_update_empty_state()` after every model mutation — delete, purge, and clear operations, not
only queue-change events:

```python
def _on_items_removed(self, *_):
    self._model.refresh()
    self._update_empty_state()  # must be called here, not only on queue events

def _on_purge(self, *_):
    self._model.clear()
    self._update_empty_state()
```

### 8. Font Size — Inherit, Don't Set

The Stage Manager sets no explicit `font_size` on cell or header labels; it inherits `omni.ui` defaults. Setting an
explicit `font_size: 12` or `font_size: 13` in a style can render **smaller** than the inherited default due to the
way Kit resolves font scaling.

Only set `font_size` for intentionally compact elements, such as badge or counter labels:

```python
# OK — deliberately small badge
style = {"font_size": 10}

# Avoid — will likely render smaller than surrounding text
style = {"font_size": 12}
```

### 9. Vertical Centering of Icons in HStack

Icons with a fixed height inside an `HStack` are top-aligned by default. Wrap them in a `VStack` with flanking
`Spacer` elements to center vertically:

```python
with ui.HStack():
    with ui.VStack(width=ui.Pixel(ICON_SIZE)):
        ui.Spacer(height=0)
        ui.Image(icon_path, width=ui.Pixel(ICON_SIZE), height=ui.Pixel(ICON_SIZE))
        ui.Spacer(height=0)
```

Apply this pattern to toolbar icons, filter icons in column headers, and any icon inside an `HStack` whose height
exceeds the icon's own height.

### 10. Menu Positioning

`ui.Menu.show()` opens at the current mouse cursor position — this is the standard pattern in this codebase. Use it
for context menus triggered by `mouse_pressed_fn`.

Do not use `ui.Menu.show_at(x, y)` together with coordinates from `mouse_pressed_fn`. The `mouse_pressed_fn` callback
provides widget-local coordinates, while `show_at` expects screen coordinates — mixing them positions the menu in the
wrong location.

```python
def _on_right_click(self, x, y, button, modifier):
    if button != 1:
        return
    menu = ui.Menu("Context Menu")
    with menu:
        ui.MenuItem("Action", triggered_fn=self._do_action)
    menu.show()  # opens at cursor — correct
    # menu.show_at(x, y)  — wrong: x/y are local, not screen coords
```

Use the `direction` parameter on `ui.Menu` to control which side of the cursor the popup opens on.

### 11. `ui.Image` — Always Set Both Width and Height

`ui.Image` renders nothing if either `width` or `height` is missing or zero. Always set both explicitly using
`ui.Pixel`:

```python
# Correct — image renders at 16x16
ui.Image("", name="MyIcon", width=ui.Pixel(16), height=ui.Pixel(16))

# Broken — missing width, image may not render
ui.Image("", name="MyIcon", height=ui.Pixel(16))
```

When the image source comes from a style (`image_url` in the style dictionary), pass `""` as the first argument.
The style's `image_url` takes effect only if both dimensions are set.

### 12. Narrow Tree Columns — Skip HStack Padding

Standard tree cells use `HStack(spacing=PADDING)` with sentinel spacers for left/right padding (see pattern 4).
However, narrow columns (e.g., 24px drag handle, 24px index) do not have enough width to fit padding + content.

For narrow columns, skip the HStack wrapper entirely and center the content directly:

```python
# For a 24px drag-handle column — no padding wrapper
if key == "drag_handle":
    with ui.ZStack(height=ui.Pixel(ROW_HEIGHT)):
        with ui.VStack():
            ui.Spacer()
            with ui.HStack(height=ui.Pixel(ICON_SIZE)):
                ui.Spacer()
                ui.Image("", name="DragHandle", width=ui.Pixel(ICON_SIZE), height=ui.Pixel(ICON_SIZE))
                ui.Spacer()
            ui.Spacer()
    return
```

Use `ZStack` for explicit height, `VStack > Spacer + content + Spacer` for vertical centering, and
`HStack > Spacer + content + Spacer` for horizontal centering.

### 13. Background Colors — Always Use ZStack with Rectangle

To set a custom background on any container (other than a button), always use a `ZStack` with a
`Rectangle` as the first child. Do NOT rely on `background_color` style properties on `ScrollingFrame`,
`Frame`, or other containers — those have their own internal backgrounds that may override or conflict.

```python
# Correct — ZStack + Rectangle for background
with ui.ZStack():
    ui.Rectangle(name="MyBackground")
    with ui.ScrollingFrame():
        # content here
```

```python
# Wrong — ScrollingFrame background_color may not render as expected
with ui.ScrollingFrame(name="MyBackground"):
    # content here — background_color from style may be overridden internally
```

Define the background color in the style dictionary on the Rectangle:

```python
"Rectangle::MyBackground": {"background_color": 0xFF202020}
```

This pattern is used consistently throughout the codebase for workspace backgrounds
(`WorkspaceBackground`), toolbar backgrounds (`QueueToolbarBackground`), footer backgrounds
(`TabBackground`), and log areas (`QueueLogBackground`).
