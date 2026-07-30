# lightspeed.trex.properties_pane.widget

Provides the RTX Remix asset-replacement Properties pane and composes its selection, layer, object, material,
particle, light, and logic panels.

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
