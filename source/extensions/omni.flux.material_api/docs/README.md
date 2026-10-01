# omni.flux.material_api

API modules for reading material properties defined in MDL (Material Definition Language) files.

## Responsibilities

- Initialize the MDL backend during extension startup, before dependent extensions resolve MDL assets or query metadata.
- Expose shader property metadata and defaults through `ShaderInfoAPI`.
- Provide placeholder attributes for displaying material properties before they are authored in USD.

## Non-Responsibilities

- Application configuration owns MDL search paths and material content locations.
- Material property widgets own selection, presentation, and editing interactions.

## Architecture

`MaterialApiExtension` calls `omni.mdl.neuraylib.ensure_running()` synchronously during startup. Consumers rely on the
extension dependency to initialize the backend; see the
[MDL startup contract](../../../../docs_dev/architecture/extension-guide.md#mdl-backend-initialization).

`ShaderInfoAPI` reads shader properties, while `PlaceholderAttribute` and `UsdShadePropertyPlaceholder` represent
properties that have not been authored in USD.

`ShaderInfoAPI(..., property_metadata_cache=...)` accepts a caller-owned dictionary for one refresh; discard it afterward.
Per-prim metadata and defaults remain isolated.
