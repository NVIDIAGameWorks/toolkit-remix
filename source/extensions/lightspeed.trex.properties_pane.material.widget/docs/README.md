# lightspeed.trex.properties_pane.material.widget

The TREX Material Properties widget wraps the USD material property widget and forwards bulk group expansion controls via
`expand_all_groups()` and `collapse_all_groups()`.

Selecting a material initializes Neuray before resolving MDL assets. This registers the MDL search paths with USD even
when a renderer has not initialized the material backend, keeping the MDL path, conversion menu, and shader properties
available on the first selection.

The **DLSS 3D-Guided Neural Generation [Experimental]** material group is shown only when the active Remix runtime
reports feature support. Legacy DLSS Neural Rendering group names remain recognized for older materials.
