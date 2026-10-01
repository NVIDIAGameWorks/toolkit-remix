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

The **DLSS 3D-Guided Neural Generation [Experimental]** material group is shown only when the active Remix runtime
reports feature support. Legacy DLSS Neural Rendering group names remain recognized for older materials.

The material action menu builds on opening and shows a loading entry until ready. Each open reads the current selection.
Selection changes, dismissal, hiding, and destruction cancel pending menu work.
Material labels and MDL paths remain available before the menu opens.
