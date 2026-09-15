# lightspeed.trex.schemas

Loads Remix-authored USD schemas and exposes their metadata to Toolkit extensions.

## Responsibilities

- Register the compiled `RemixParticleSystem` USD plugin.
- Provide particle schema attribute and type lookup helpers.
- Parse the packaged generated `RemixCategories` schema into Toolkit category metadata.
- Keep Remix category names, attributes, and descriptions synchronized with HdRemix.
- Maintain the explicit list of deprecated Remix categories and expose the subset available for new assignment.

## Non-Responsibilities

- Defining Toolkit UI policy such as supported prim types or hidden categories.
- Authoring or maintaining the upstream Remix schemas.
- Providing category assignment UI.

## Architecture

- `extension.py` owns the schema registry lifecycle.
- `plugin.py` registers compiled USD schema plugins and their source schemas.
- `particle.py` exposes particle schema attributes and types.
- `categories.py` parses `/RemixInstanceCategoryAPI` from the packaged HdRemix schema. Descriptions wrap to 60
  characters so info-icon tooltips retain a compact visual block. Missing or malformed category schemas log an error
  and expose empty mappings without blocking Toolkit startup. The complete mapping retains deprecated metadata for
  compatibility migrations, while the assignable mapping excludes deprecated categories from new authoring. The
  schema attribute `remix_category:decal_Static` is exposed with its canonical display label, `Decal`.
- `utils.py` resolves registered schema prim definitions.
