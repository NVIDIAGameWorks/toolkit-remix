# lightspeed.trex.app.style

Defines the shared NVIDIA RTX Remix application palette and named widget styles.

## Responsibilities

- Set application colors, fonts, icons, and widget interaction styles.
- Adapt popup dialogs and viewport menus to the Remix theme.
- Own normal Curve Editor channel colors and their selected-label variants.

## Non-Responsibilities

Widget extensions own layout, selection behavior, and data editing. The
[Curve Editor](../../omni.flux.curve_editor.widget/docs/README.md#channel-styling) owns channel label selection states.
The application resource extension owns font assets. Nickname editing and other reusable Flux controls belong to
their widget extensions.

## Architecture

- `trex_style.py` registers named selectors in the shared `omni.ui.Style` default dictionary when imported.
- `override_dialog_get_style()` applies the application theme to popup dialog styles.
- `update_viewport_menu_style()` configures the shared viewport menu palette.

`trex_style` exports the shared `style` object and styling helpers. Resource lookup uses
`omni.flux.utils.widget`; the host application selects the resource extension.

## Curve Channel Palette

`trex_style.py` defines normal `Label::<name>` colors and selected-label overrides in `0xAABBGGRR` byte order.

| Style name | Channels | Selected label |
| --- | --- | --- |
| `CurveEditorChannelX` | Size and velocity X | Pale coral (`#FFD4CC`) |
| `CurveEditorChannelY` | Size and velocity Y | Light lime (`#C8EDAA`) |
| `CurveEditorChannelZ` | Velocity Z | Light blue (`#CEDFFF`) |
| `CurveEditorRotationMinimum` | Minimum rotation speed | Normal color |
| `CurveEditorRotationMaximum` | Maximum rotation speed | Normal color |

The [particle panel](../../lightspeed.trex.properties_pane.particle.widget/docs/README.md) assigns these semantic
names; the [USD layout adapter](../../omni.flux.property_widget_builder.model.usd/docs/README.md#curve-layout-styling)
resolves their normal colors when constructing property controls.
