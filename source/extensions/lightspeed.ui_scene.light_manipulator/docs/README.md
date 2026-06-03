# lightspeed.ui_scene.light_manipulator

Viewport scene manipulators for selected USD lights. The extension draws transform, size, intensity,
and spotlight-cone controls in the active viewport.

## Responsibilities

- Create and update light manipulators for selected `UsdLux` prims.
- Author light transform, size, intensity, exposure, color, color temperature, and shaping attributes through the model layer.
- Draw spotlight cone wireframes for DiskLight and SphereLight prims when a valid shaping cone angle is authored.
- React to persistent viewport settings for manipulator visibility, intensity controls, cone visibility, cone threshold, cone subdivisions, and cone colors.
- Register the Display menu entry that exposes spotlight-cone threshold, subdivision, and color controls when the viewport menubar extension is available.

## Non-Responsibilities

- Creating or deleting light prims.
- Owning the Show-By-Type Lights menu. `lightspeed.light.gizmos` owns that menu and exposes the shared `Spotlight Cones` visibility toggle there.
- Persisting project data outside USD attributes and carb settings.
- Rendering light icons or non-selected light gizmos.

## Architecture

- `LightManipulatorLayer` owns viewport-layer lifecycle, selection tracking, carb-setting subscriptions, and manipulator creation.
- `AbstractLightModel` and subclasses read and author USD light attributes. `ShapingMixin` reads authored shaping cone attributes directly so property-panel-authored spotlights work even when the API schema was not formally applied.
- `AbstractLightManipulator` and subclasses build the `omni.ui.scene` geometry for each light type.
- `compute_luminance` and `compute_threshold_distance` convert light color, temperature, exposure, intensity, radius, and cone threshold into spotlight-cone display distance.
- `viewport_menu.py` registers the Display menu controls for cone threshold, subdivisions, and colors.

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `/persistent/app/viewport/manipulator/lightManipulatorsVisible` | `true` | Show selected-light manipulators. |
| `/persistent/app/viewport/manipulator/lightIntensityControlsVisible` | `false` | Show full intensity controls instead of minimal intensity indicators. |
| `/persistent/app/viewport/manipulator/spotlightConeVisible` | `true` | Show spotlight cone wireframes. The Show-By-Type toggle is owned by `lightspeed.light.gizmos`. |
| `/persistent/app/viewport/manipulator/spotlightConeIlluminanceThreshold` | `0.1` | Lux threshold used to size the cone display distance. |
| `/persistent/app/viewport/manipulator/spotlightConeSides` | `32` | Cone radial subdivisions, clamped to the supported UI range. |
| `/persistent/app/viewport/manipulator/spotlightConeOuterColor` | `[0.0, 1.0, 0.0]` | Outer cone RGB color. |
| `/persistent/app/viewport/manipulator/spotlightConeInnerColor` | `[0.0, 1.0, 1.0]` | Inner cone RGB color for softness. |

## Known Limitations

- Spotlight cones are visualization aids, not exact renderer debug overlays.
- Cone-capable manipulators rely on physically proportional light models so photometric cone distances remain in stage units and are not affected by the global manipulator scale.
