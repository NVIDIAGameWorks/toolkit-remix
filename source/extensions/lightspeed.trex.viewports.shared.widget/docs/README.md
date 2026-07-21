# lightspeed.trex.viewports.shared.widget

Provides the shared RTX Remix viewport UI, including its viewport layers, tools, statistics, and adjacent Properties
pane.

If the active viewport camera is the capture game camera, camera-mutating gestures and frame/focus actions first copy
that view to `/OmniverseKit_Persp` and switch the viewport to perspective. Plain viewport focus keeps looking through
the capture game camera, which remains read-only source data. If the copy to perspective cannot be completed, the
camera-mutating action is canceled and a warning explains that the capture game camera was kept read-only.

## Responsibilities

- Build and manage shared RTX Remix viewport instances.
- Host the viewport/Properties pane splitter and keep the Properties pane at least 240 pixels wide.
- Coordinate viewport layers, tools, statistics, activation, and renderer startup behavior.
- Protect capture game-camera source data while still allowing mutating camera workflows through perspective copies.

## Non-Responsibilities

- Defining the property editors displayed inside the Properties pane.
- Owning USD property models or property-widget delegates.

## Architecture

- `SetupUI` builds the viewport, Properties pane, and splitter and coordinates their lifecycle.
- `ViewportLayers` owns the registered viewport-layer instances and their ordering.
- The `scene`, `stats`, and `tools` packages provide the viewport overlays and interactions hosted by `SetupUI`.