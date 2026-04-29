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
