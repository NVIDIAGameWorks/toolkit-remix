# lightspeed.trex.properties_pane.widget

Provides the RTX Remix asset-replacement Properties pane and composes its selection, layer, object, material,
particle, light, and logic panels.

The Object, Material, Particle, and Logic Properties section header `More` menus expose `Expand All` and `Collapse All`
actions for their property groups. The Particle Properties menu also keeps the particle system definition transfer action
when a transfer target is available.

## Responsibilities

- Select and display the property panels relevant to the current USD selection.
- Preserve collapsible-panel state and coordinate property-panel interactions.
- Keep horizontal scrolling disabled while clipping overflowing content within the pane hierarchy.

## Non-Responsibilities

- Defining the responsive sizing or component-level clipping of individual property widgets.
- Controlling the minimum width of the viewport/Properties pane splitter.

## Architecture

- `AssetReplacementsPane` builds the pane, owns the root scrolling frame, and responds to USD selection changes.
- Specialized property-widget extensions supply the editors hosted in each collapsible panel.
- The shared viewport extension owns the surrounding viewport/Properties pane splitter.

Selection changes close floating Curve and Gradient editors even when the pane is pinned. The pane stays pinned;
reopening edits its original targets. Closing or replacing the owning USD stage clears the Object, Material, Particle,
and Logic pins and property targets, even when the pane is hidden or a section is collapsed. See the
[shared window](../../omni.flux.property_widget_builder.delegates/docs/README.md#floating-property-editors).
