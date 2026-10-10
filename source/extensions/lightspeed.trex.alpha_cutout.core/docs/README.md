# lightspeed.trex.alpha_cutout.core

Turns an alpha-tested capture mesh into geometry that is cut along the alpha channel of its diffuse texture, writes
the result as an ingested replacement file and swaps the capture reference for it.

## Responsibilities

- Read the geometry, texture coordinates, normals, transform and bound material of a `mesh_HASH` capture prototype
  into plain numpy arrays (`usd_reader`).
- Decode the diffuse texture alpha, trace the opaque texels into simplified polygons with holes and clip every
  triangle against that region in UV space, lifting the pieces back to 3D barycentrically (`mask`, `simplify`,
  `triangulate`, `cut`, `converter`).
- Optionally extrude the cut mesh backwards into side quads with or without a back face (`thicken`), smooth the
  normals of the result and blend all normals towards the stage up axis (`normals`).
- Write the cut mesh, a flattened copy of the captured material and the `.meta` ingestion sidecar as a standalone
  `cutout_<HASH>.usda` (`usd_writer`, `material_copy`).
- Convert replacement meshes too: resolve a selected prim to its capture prototype or to the `ref_*` prim of a
  replacement (`ConversionTarget`), read the replacement geometry from the untouched original file, and write a
  copy of that file named `<name>_cutout_replacement<ext>` in which only the converted meshes change
  (`usd_reader`, `usd_writer.write_cutout_replacement`).
- Mask the capture reference and reference the generated file on the current edit target through the undoable
  commands of the asset replacement core, reusing an existing reference on re-conversion (`stage_edits`).

## Non-Responsibilities

- Does not create any UI. `lightspeed.trex.alpha_cutout.widget` owns the window and the parameters.
- Does not decide which meshes to convert. The Stage Manager plugin in `lightspeed.trex.stage_manager.plugin.widget.usd`
  resolves the selection.
- Does not add pip packages. It relies on the numpy, shapely and Pillow builds that `omni.flux.pip_archive` provides.
- Does not override the captured material. The generated file binds its own material copy.

## Architecture

### Threading contract

`read_mesh_sources` and `write_cutout_mesh` touch USD and run on the main thread. `convert_meshes` runs on a worker
thread through `run_worker_with_latest_progress` and only sees the frozen dataclasses in `data_models`, which hold
numpy arrays and strings. Keep every `pxr` call out of the worker.

### Key Classes and Functions

- `CutoutParameters` — the tunable settings of a run.
- `MeshSource` — everything the worker needs about one mesh, with a `skip_reason` when it cannot be converted.
- `read_mesh_source` — reads the geometry from the mesh file the capture layer references, not from the composed
  prototype, so a mesh whose capture reference is already masked by an earlier conversion still yields the original
  cards. Values come from the default time code with a fallback to the first time sample. The material is the one
  bound to the prototype in the project stage, user overrides included.
- `trace_alpha_mask` — traces the interpolated iso contour of the downscaled alpha with marching squares, so
  diagonal edges are straight lines rather than texel staircases, polygonizes it with shapely, keeps the opaque
  faces, simplifies the outline and applies the edge margin as a mitred buffer.
- `simplify_ring_minimal` — Imai-Iri optimal simplification used when the minimal outline option is on: a
  Douglas-Peucker pass at a twentieth of the tolerance thins the raw contour, then the fewest-vertex path
  through the chords that keep every skipped vertex within the rest of the tolerance is taken. Chords are
  tested with the angular cone intersection and verified against the segment only when the contour reaches
  past the chord end.
- `cut_triangles` — clips each triangle only against the polygons an `STRtree` reports as intersecting it, so the
  cost scales with the local outline instead of the whole texture.
- `union_geometries` — pairwise union through the binary `union` ufunc. The bundled shapely 2.0.5 cannot build
  geometry collections under numpy 2, so every `unary_union` style call fails and must not be used.
- `earclip_polygon_with_holes` — a port of Mapbox earcut (z-order hashed ear clipping with hole elimination, local
  intersection curing and polygon splitting); no third-party triangulator is available, and a simpler hand-written
  bridging lost large areas on polygons with many holes.
- `cut_triangles` — clips each triangle, tiles the mask when texture coordinates leave the unit square, preserves the
  winding of mirrored UV triangles and welds the output vertices.
- `thicken_mesh` — groups vertices by position so UV seams do not count as boundary edges, offsets every
  position against its area-weighted face normal, adds two outward-facing triangles per boundary edge and an
  optional reversed back copy. Side texture coordinates either repeat the edge or, with anti-stretch, sample
  the band inside the outline at the face's texel density.
- `smooth_normals` / `bend_normals_up` — blend the current normals towards the area-weighted average around
  each position, or towards the stage up axis expressed in mesh space through the prototype transform. Both
  derive normals from the faces when the mesh has none. The up blend ignores instance placement, so a
  prototype instanced with rotations receives the up direction of its own prim space.
- `resolve_conversion_target` — a mesh under a Remix reference prim is a replacement unless the reference points
  at a capture cutout this tool wrote; the original file is the referenced file with the
  `_cutout_replacement` suffix stripped, so a reference that already points at a cutout still converts from the
  original. Candidate meshes are the Mesh prims under the reference prim that are not skinned, have no
  `GeomSubset` children and whose composed material has a diffuse texture.
- `write_cutout_replacement` — `TransferContent` of the original layer into the cutout layer keeps prim names,
  materials and relative texture paths, so overrides authored under the `ref_*` prim keep applying after the
  reference swap. Materials bound from outside the file keep their alpha state.
- `AlphaCutoutStageEditor.apply` — swaps replacement references with `replace_reference` on the existing
  `ref_*` prim (`remove_if_remix_ref=False`, `create_if_remix_ref=False`); capture references are masked and a
  new `ref_*` child is added as before.
- `copy_material_flattened` — copies the composed shader attributes so user overrides on the captured material are
  baked in, rewrites asset paths relative to the generated file and optionally authors the opaque alpha state.
- `write_cutout_mesh` — mirrors the ingestion layout (`ReferenceTarget` ▸ `XForms` ▸ `cutout_<HASH>` with identity
  translate, rotate and scale ops) so the toolkit treats the file like an ingested asset. The cutout prim and the
  material `AlphaCutoutMaterial` avoid the capture naming scheme on purpose:
  prims named `mesh_HASH` or `mat_HASH` would be classified as capture prims by the toolkit. It reuses the layer when
  the project already holds the file open so the stage recomposes immediately.
- `AlphaCutoutStageEditor` — groups the reference commands in one undo group and refuses edit targets that are not
  replacement layers.

### Alpha state

The runtime deserializes `inputs:alpha_test_type` as a raw integer and its `AlphaTestType::kAlways` is `7`, while the
MDL enum lists `Always` first. `ALPHA_TEST_ALWAYS` therefore is `7`; the material property panel labels that value
with the MDL name `Greater Or Equal`.

## Usage

```python
from lightspeed.trex.alpha_cutout.core import (
    AlphaCutoutStageEditor, CutoutParameters, convert_meshes, read_mesh_sources, write_cutout_mesh,
)

sources = read_mesh_sources(stage, ["/RootNode/meshes/mesh_CED45075A077A49A"])
results = convert_meshes(sources, CutoutParameters(), queue_progress=lambda *_: None, is_cancelled=lambda: False)
written = [
    result.with_output_path(write_cutout_mesh(output_dir, result.source, result.cut_mesh, stage, True))
    for result in results
    if result.cut_mesh is not None
]
AlphaCutoutStageEditor(context_name).apply(written)
```

## Known limitations

- Skinned meshes, meshes without texture coordinates and materials without a diffuse texture are skipped.
- Animated captures convert their first time sample only.
- The generated `.usda` and `.meta` files are not removed by undo.
