# lightspeed.trex.viewports.properties_pane.render.widget

Builds the viewport **Render Settings** properties pane for RTX Remix Toolkit.

## Responsibilities

- Provide the visible Render Settings pane in the viewport properties panel.
- Expose global experimental DLSS NR controls when the running renderer reports the feature as available.
- Persist those controls through the shared `lightspeed.hdremix.renderer_settings` carb settings.

## Non-Responsibilities

- Does not push renderer config values directly; `lightspeed.hdremix.renderer_settings` owns the runtime bridge.
- Does not author per-material DLSS NR control masks.
- Does not manage the viewport render menubar.

## Architecture

- `RenderPane`: owns the render settings UI frame and presents the shared DLSS Neural Rendering controls.
- `lightspeed.hdremix.renderer_settings`: owns the persistent settings and runtime synchronization.

## Settings

The pane uses the same persistent settings as **Edit > Preferences > HdRemix Renderer**. See the [renderer settings documentation](../../lightspeed.hdremix.renderer_settings/docs/README.md#dlss-3d-guided-neural-generation-experimental) for paths, defaults, runtime mappings, and constraints.
