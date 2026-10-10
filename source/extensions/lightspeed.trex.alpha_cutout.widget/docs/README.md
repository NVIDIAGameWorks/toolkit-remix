# lightspeed.trex.alpha_cutout.widget

Dockable **Convert Alpha Cards to Mesh** window that converts the selected capture mesh with the exposed parameters
through `lightspeed.trex.alpha_cutout.core`.

## Responsibilities

- Register the window with the Kit workspace and the `Window > Experimental` menu, so layouts can dock and reopen it.
- Open the window seeded with prototype paths when `GlobalEventNames.ALPHA_CUTOUT_CONVERT_REQUEST` fires.
- Follow the USD selection while the window is visible: the first selected capture mesh, instance or replacement
  mesh is the target up for conversion, and a selection without one clears it.
- List the meshes of the target as ticked checkbox rows; a replacement lists every mesh of its file that has a
  diffuse texture, and unticked meshes are copied into the cutout file unchanged.
- Lock the output field to `<name>_cutout_replacement<ext>` next to the original for replacements, which are
  never overwritten.
- Show a reset dot next to every parameter that differs from its default (click resets it). The THICKEN header
  reads `THICKEN (ON)` or `THICKEN (OFF)` so the collapsed section still shows whether thickening is active.
- Persist the output folder and the conversion parameters under
  `/persistent/exts/lightspeed.trex.alpha_cutout.widget/`.
- Drive one conversion at a time: read the mesh on the main thread, run the worker behind a cancellable progress
  popup, write the file, apply the stage edits and show the outcome.

## Non-Responsibilities

- Does not trace, cut or write geometry. `lightspeed.trex.alpha_cutout.core` owns that.
- Does not inspect the Stage Manager selection. The context-menu plugin in
  `lightspeed.trex.stage_manager.plugin.widget.usd` resolves it and sends the event.
- Does not validate the output folder beyond path syntax; the writer creates it when missing.

## Architecture

- `AlphaCutoutWidgetExtension` creates `AlphaCutoutWindow`, registers its show function and subscribes to the
  conversion request event.
- `AlphaCutoutWindow` is a `WorkspaceWindowBase`. `open_with_meshes` rebuilds the pane when the request comes from
  another USD context, shows and focuses the window and sets the mesh up for conversion. On its first show the
  window docks itself right of the Viewport unless the layout already placed it.
- `AlphaCutoutPane` is the `WorkspaceWidget`. It builds the SELECTED MESH, OUTPUT FOLDER, PARAMETERS, THICKEN, NORMALS
  and RESULTS sections, styles its drag fields like the material property fields, keeps the Convert button disabled while a run is active, nothing is selected or the folder is invalid,
  and only starts a run when the edit target is a replacement layer.
- `AlphaCutoutSettings` wraps the persistent carb settings and converts them into `CutoutParameters`.

## Settings

| Setting path | Default | Description |
|---|---|---|
| `exts.lightspeed.trex.alpha_cutout.widget.output_folder` | `""` | Output folder; empty means `<project>/assets/ingested/alpha_cutout` |
| `exts.lightspeed.trex.alpha_cutout.widget.alpha_threshold` | `128` | Alpha value at or above which a texel is opaque |
| `exts.lightspeed.trex.alpha_cutout.widget.trace_resolution` | `256` | Longest side of the traced mask in texels |
| `exts.lightspeed.trex.alpha_cutout.widget.simplify_tolerance` | `1.0` | Outline simplification tolerance in texels |
| `exts.lightspeed.trex.alpha_cutout.widget.edge_margin` | `1.0` | Outline growth in texels, negative shrinks |
| `exts.lightspeed.trex.alpha_cutout.widget.min_island_area` | `4.0` | Smallest kept island in texels |
| `exts.lightspeed.trex.alpha_cutout.widget.disable_alpha_test` | `true` | Author the opaque alpha state on the material copy |
| `exts.lightspeed.trex.alpha_cutout.widget.minimal_outline` | `true` | Simplify the outline to the fewest vertices within the tolerance |
| `exts.lightspeed.trex.alpha_cutout.widget.thicken` | `false` | Extrude the cut mesh backwards |
| `exts.lightspeed.trex.alpha_cutout.widget.thickness` | `1.0` | Extrusion distance in mesh units |
| `exts.lightspeed.trex.alpha_cutout.widget.thicken_back_face` | `true` | Close the extrusion with a back face |
| `exts.lightspeed.trex.alpha_cutout.widget.thicken_anti_stretch` | `false` | Texture the sides with a band inside the outline |
| `exts.lightspeed.trex.alpha_cutout.widget.smooth_normals` | `false` | Smooth the normals of the thickened mesh |
| `exts.lightspeed.trex.alpha_cutout.widget.smoothing` | `1.0` | Normal smoothing strength from 0 to 1 |
| `exts.lightspeed.trex.alpha_cutout.widget.up_normals` | `false` | Blend the normals towards the stage up axis |
| `exts.lightspeed.trex.alpha_cutout.widget.up_amount` | `1.0` | Up-facing blend strength from 0 to 1 |

## Known limitations

- The stage edits of a run undo as one group; the generated files stay on disk.
- Converting the same mesh again overwrites its file and keeps the existing reference.
