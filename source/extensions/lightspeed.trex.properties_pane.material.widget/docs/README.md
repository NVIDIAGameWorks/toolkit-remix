# lightspeed.trex.properties_pane.material.widget

The TREX Material Properties widget adapts the USD material property widget for Remix material selection and actions.

## Responsibilities

- Display the selected material's properties, label, and MDL path.
- Provide material actions and runtime-dependent property groups.
- Forward bulk group expansion controls through `expand_all_groups()` and `collapse_all_groups()`.

## Non-Responsibilities

- [The material API](../../omni.flux.material_api/docs/README.md) owns MDL backend initialization during startup.
- Application configuration owns MDL search paths and material content locations.

## Architecture

`SetupUI` wraps `omni.flux.properties_pane.materials.usd.widget`, whose dependency on `omni.flux.material_api` establishes
MDL initialization before this widget starts. Material selection can resolve MDL assets without initializing Neuray.

The **DLSS 3D-Guided Neural Rendering** material group is shown only when the active Remix runtime
reports feature support. Older Neural Generation, experimental, and legacy DLSS Neural Rendering group names remain
recognized for older materials.

SSS property visibility follows the shader's `inputs:subsurface_diffusion_profile` value. Thin Opaque materials show
single-scattering and thickness controls; Diffusion Profile materials show transmittance and radius controls.
The custom field builder hides properties belonging to the other mode.

The material action menu builds on opening and shows a loading entry until ready. Each open reads the current selection.
Selection changes, dismissal, hiding, and destruction cancel pending menu work.
Retired menus hide immediately and release their widgets on the next UI update, after active callbacks finish.
Material labels and MDL paths remain available before the menu opens.

## Usage

See [Texture Transform](../../../../docs/howto/learning-materials.md#texture-transform) for material controls and
[Updating Capture Material Definitions](../../../../docs/howto/learning-materials.md#updating-capture-material-definitions)
when an older capture does not expose newly added properties.
