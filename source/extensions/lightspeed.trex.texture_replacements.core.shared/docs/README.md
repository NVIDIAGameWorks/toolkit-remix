# lightspeed.trex.texture_replacements.core.shared

Shared texture discovery, validation, and USD mutation logic for RTX Remix applications.

## Responsibilities

- Discover texture shader inputs and their resolved asset paths in an explicit USD context.
- Validate shader input paths, texture assets, texture types, and project-layer filters.
- Accept authored Asset/String shader inputs and use canonical material shader metadata to resolve unauthored inputs.
- Replace or remove texture opinions atomically through Kit commands and the current or caller-provided edit layer.
- Define the request and response models shared by direct callers and the texture replacement service.

## Non-Responsibilities

- Does not expose HTTP endpoints. `lightspeed.trex.texture_replacements.service` owns REST routing and status mapping.
- Does not ingest or convert source textures. `lightspeed.trex.asset_pipeline.core` owns Remix asset processing and
  produces validated texture outputs.
- Does not communicate with ComfyUI or own queue jobs. `lightspeed.trex.comfyui.core` owns that workflow.
- Does not render texture replacement UI.

## Architecture

`TextureReplacementsCore` binds discovery and mutation to an explicit USD context. Direct callers can filter authored
Asset/String shader inputs, with canonical material metadata as the fallback for unauthored inputs, before processing
assets. Replacements are applied in one undo group on the current or caller-provided edit layer. A failed command rolls
the complete batch back and cannot be redone.
Duplicate shader-input targets are rejected before command dispatch. Forced replacement is reserved for guarded writes
such as restoring a recorded authored path: callers must provide `expected_current_textures` for the exact target-layer
baseline. The core checks that baseline before dispatch and the command checks it again immediately before mutation.
Force bypasses source availability and ingestion checks, but never ownership confirmation, path, shader-input,
value-type, or texture-suffix validation.

### Key Classes

- `TextureReplacementsCore` is the context-bound entry point for discovery, valid-input filtering, and USD mutation.
- `TextureReplacementsValidators` validates USD shader properties, texture assets, and project-layer membership.
- `ReplaceTexturesRequestModel` carries validated replacements and the expected target-layer baseline required by force.
- `TexturesResponseModel`, `PrimPathsResponseModel`, and `TextureTypesResponseModel` define stable service responses.
