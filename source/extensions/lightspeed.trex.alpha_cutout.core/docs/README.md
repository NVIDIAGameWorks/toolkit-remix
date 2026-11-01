# lightspeed.trex.alpha_cutout.core

Cuts alpha-tested meshes along the alpha channel of their diffuse texture so only the opaque area remains as
geometry. The `Alpha Card to Mesh` asset modifier in `lightspeed.trex.alpha_cutout.modifier` drives it.

## Responsibilities

- Decode the diffuse texture alpha, trace the opaque texels into simplified polygons with holes and clip every
  triangle against that region in UV space, lifting the pieces back to 3D barycentrically (`mask`, `simplify`,
  `triangulate`, `cut`, `converter`).
- Optionally extrude the cut mesh backwards into side quads with or without a back face (`thicken`), smooth the
  normals of the result and blend all normals towards the stage up axis (`normals`).
- Read the geometry of a mesh from its model file into plain numpy arrays (`usd_reader`), capture the composed
  material of a mesh as JSON-compatible data and rebuild it (`material_snapshot`), and write a flattened copy of
  the model file with the cut geometry authored on the converted meshes (`cutout_file`).

## Non-Responsibilities

- Does not decide which meshes to convert, where the output goes, or how it is published and referenced. The
  Asset Modifiers framework resolves the selection, runs the job in the Job Queue, optimizes and publishes the
  output through the asset pipeline and replaces the reference.
- Does not copy or convert textures and does not write `.meta` sidecars; the asset pipeline does.
- Owns no UI and no settings.

## Architecture

`convert_mesh` runs on a worker thread and touches no USD object. `read_mesh_source`, `snapshot_material` and
`write_cutout_file` touch USD and run where the caller holds the stage.

- `trace_alpha_mask` — traces the interpolated iso contour of the downscaled alpha with marching squares, so
  diagonal edges are straight lines rather than texel staircases, polygonizes it with shapely, keeps the opaque
  faces, simplifies the outline and applies the edge margin as a mitred buffer.
- `simplify_ring_minimal` — Imai-Iri optimal simplification used when the minimal outline option is on: a
  Douglas-Peucker pass at a twentieth of the tolerance thins the raw contour, then the fewest-vertex path
  through the chords that keep every skipped vertex within the rest of the tolerance is taken.
- `earclip_polygon_with_holes` — a port of Mapbox earcut (z-order hashed ear clipping with hole elimination,
  local intersection curing and polygon splitting); no third-party triangulator is available, and a simpler
  hand-written bridging lost large areas on polygons with many holes.
- `union_geometries` — pairwise union through the binary `union` ufunc. The bundled shapely 2.0.5 cannot build
  geometry collections under numpy 2, so every `unary_union` style call fails and must not be used.
- `cut_triangles` — clips each triangle only against the convex pieces an `STRtree` reports as intersecting it,
  tiles the mask when texture coordinates leave the unit square, preserves the winding of mirrored UV triangles
  and welds the output vertices.
- `thicken_mesh` — groups vertices by position so UV seams do not count as boundary edges, offsets every position
  against its area-weighted face normal, adds two outward-facing triangles per boundary edge and an optional
  reversed back copy. Side texture coordinates either repeat the edge or, with anti-stretch, sample the band
  inside the outline at the face's texel density.
- `smooth_normals` / `bend_normals_up` — blend the current normals towards the angle-weighted average around each
  position, or towards the stage up axis expressed in mesh space through the mesh transform.
- `snapshot_material` — stores the composed surface shader of a material as plain data so a job can carry it:
  textures as absolute paths, MDL modules as bare names. `define_material` rebuilds it through the shader schema
  so the asset pipeline recognizes the Aperture shader and keeps its inputs, and optionally authors
  `use_legacy_alpha_state = false`, `blend_enabled = false` and `alpha_test_type = 7`, which the runtime reads as
  "always pass".
- `write_cutout_file` — flattens the model file, rewrites the converted meshes, defines a material from the
  snapshot for capture meshes and authors the opaque alpha state on the file's own Aperture material otherwise.
  Textures are copied into a `textures` folder next to the output and referenced by absolute path, so the
  pipeline publishes them beside the mesh instead of under an external hash folder. Every converted mesh gets
  custom string attributes naming the model file, the prim and the project material it was made from
  (`read_origin`), which the modifier uses to start a later run from the original again.

## Limitations

- Skinned meshes, meshes with geometry subsets and meshes without texture coordinates are not converted.
- Animated meshes convert their first time sample.
- Pillow decodes the common DDS block formats; textures it cannot decode fail the job.
