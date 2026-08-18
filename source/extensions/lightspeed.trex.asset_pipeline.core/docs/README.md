# lightspeed.trex.asset_pipeline.core

Remix-specific asset processing pipeline foundations.

This extension owns the concrete Remix contract on top of the generic Flux
pipeline base. The pipeline is one linear list of steps over one stable
`RemixAssetItem` type. The same item type covers standalone textures, ComfyUI
image outputs, model files, model-referenced textures, and embedded model
textures once the importer materializes them as files.

## Responsibilities

- Define Remix asset item types: `RemixAssetItem`, `TextureAsset`, and `TextureBinding`.
- Define explicit enums for Remix pipeline contracts: `AssetKind` and `MaterialType`.
- Provide the canonical step order through `build_remix_asset_pipeline()`.
- Run the canonical steps through `run_remix_asset_pipeline()`, which owns the
  temporary workspace, final reported publish phase, progress forwarding, and
  temporary-file cleanup.
- Expose `TextureProcessingJob` with exact texture-only queue ports, immutable
  source/result records, stable item keys, and local or remote publication.
- Implement the asset processing foundations: input standardization, model
  processing, normal OTH conversion, DDS conversion, reference rewriting, and
  metadata sidecars.
- Keep blocking normal and DDS converters off the caller's event-loop thread.
- Read shader identifiers directly from authored USD data without loading UI material-library modules.

## Non-Responsibilities

- Does not define the generic pipeline framework; that lives in `omni.flux.asset_pipeline.core`.
- Does not assign ComfyUI outputs to shader inputs. The ComfyUI apply handler owns guarded live-stage replacement.
- Does not delete caller-owned source files. The runner deletes only its own temporary workspace.
- Does not own graph execution, fan-out, dependencies, or aggregation; the job queue owns that.
- Does not provide generic reusable asset processing for every product. This is Remix-specific.

## Core Structure

```text
+---------------------------+
| RemixAssetItem            |
| kind: AssetKind           |
| value: primary path       |
| source_path: original     |
| material_type: enum      |
| textures: TextureAsset[]  |
| bindings: TextureBinding[]|
+------------+--------------+
             |
             | stable item object flows through every step
             v
+---------------------------+
| TextureAsset              |
| path: current image path  |
| texture_type: TextureTypes|
| original_path: first path |
+---------------------------+
             ^
             |
+---------------------------+
| TextureBinding            |
| shader_path: Sdf.Path     |
| input_name: str           |
| original_asset_path: Sdf  |
| texture: TextureAsset     |
+---------------------------+
```

The conversion steps operate on `TextureAsset` records. They do not care whether
the image came from Asset Library, ComfyUI, a model reference, or an embedded
model texture.

## Workspace And Publishing

Steps do not create the final output directory and do not own cleanup policy.
The Remix runner creates one temporary work directory, gives it to the context,
then publishes only the final paths still referenced by `RemixAssetItem` and
`TextureAsset` records. Sidecar `.meta` files for those final paths are moved
with them. Anything else left in the temporary directory is an intermediate and
is removed when the runner exits.

Steps also do not invent temporary filename collision rules. When a step needs a
publishable derived file, it asks
`RemixAssetPipelineContext.reserve_output_path()` for both paths: `work_path` is
the temporary file the step writes, and `output_path` is the final path the
runner will publish to. The context keeps readable file names inside per-source
workspace directories, so two inputs named `albedo.png` cannot overwrite each
other during conversion. `copy_to_work_dir()` uses the same policy for existing
DDS files or other caller-owned inputs. When a step needs to copy a reusable
final file into an already-reserved derived path, it uses `copy_to_work_path()`
so publish reservations stay stable.

Final publishing is also pipeline-owned. Each `TextureProcessingRequest` carries
a stable project or import root. The context preserves every source's path
relative to that root and includes the processing semantic in derived names,
for example `textures/chair/albedo.diffuse.dds`. Independent jobs therefore map
the same source and semantic to the same reusable destination without allowing
same-named sources from other folders to overwrite it. A stable source-path
hash remains the fallback only for a genuine collision after that mapping.
Steps never choose deduplication suffixes. If a step needs to probe a reusable
final file from an earlier run, it uses the `output_path` from its reservation.
The runner uses the same reservation table for local and remote publication.

When a step needs to author a reference from one published output to another,
for example a model USD file pointing at a processed texture, it uses
`RemixAssetPipelineContext.get_relative_output_asset_path()`. That method
reserves both final paths and computes the asset reference against the final
published locations, not the temporary workspace.

Existing final DDS files are reused only when their sidecar metadata matches the
current source hash, texture type, and NVTT arguments. A name match alone is not
treated as a valid cache hit.

```text
caller input files
        |
        v
+-----------------------------+
| run_remix_asset_pipeline()  |
| creates temp work_dir       |
+-------------+---------------+
              |
              v
+-----------------------------+
| pipeline steps              |
| write outputs to work_dir   |
| update item/texture paths   |
+-------------+---------------+
              |
              v
+-----------------------------+
| publish final item paths    |
| + matching .meta files      |
| final reported phase        |
+-------------+---------------+
              |
              v
output_dir/source-relative/final files

temp work_dir/intermediates -> deleted by runner cleanup
```

## Stage Access And Performance

Model steps may need to read or mutate a full USD stage, but they must not open
the model through the app's default USD context. The user can have an
interactive work-in-progress stage open while ingestion runs in the background.
Opening into the default context would replace or disturb that stage.

`RemixAssetPipelineContext` owns one uniquely named ingestion USD context per
pipeline run:

```text
job queue pipeline A              job queue pipeline B
        |                                  |
        v                                  v
+----------------------+          +----------------------+
| RemixAssetPipeline   |          | RemixAssetPipeline   |
| Context A            |          | Context B            |
| stage context name   |          | stage context name   |
| remix_asset_..._uuid |          | remix_asset_..._uuid |
+----------+-----------+          +----------+-----------+
           |                                 |
           v                                 v
+----------------------+          +----------------------+
| ingestion USD context|          | ingestion USD context|
| cached current stage |          | cached current stage |
+----------------------+          +----------------------+
```

The cache is intentionally per pipeline context, not global. That keeps parallel
job-queue pipelines isolated while still avoiding repeated
create/open/close/destroy cycles between adjacent model steps in the same
pipeline. Steps call `context.open_stage()`; they do not call
`Usd.Stage.Open()` directly. The runner closes and destroys the ingestion
context before deleting the temporary workspace.

## Canonical Pipeline

```text
RemixAssetItem
      |
      v
+-----------------------------+
| StandardizeInputStep        |
| texture: create records     |
| model: import to USD        |
+-----------------------------+
      |
      v
+-----------------------------+
| TriangulateMeshesStep       |  model-only
+-----------------------------+
      |
      v
+-----------------------------+
| ConvertMaterialsStep        |  model-only
+-----------------------------+
      |
      v
+-----------------------------+
| CollectTexturesStep         |  model-only
+-----------------------------+
      |
      v
+-----------------------------+
| ConvertNormalStep           |  all texture records
+-----------------------------+
      |
      v
+-----------------------------+
| ConvertDDSStep              |  all texture records
+-----------------------------+
      |
      v
+-----------------------------+
| UpdateTexturesStep          |  model bindings
+-----------------------------+
      |
      v
+-----------------------------+
| WriteMetadataStep           |  final textures/models
+-----------------------------+
      |
      v
+-----------------------------+
| Publish processed assets    |  final phase, blocking I/O off-loop
+-----------------------------+
```

Model-only steps skip with an explicit reason for texture-only runs.

## Input Flows

```text
Standalone texture or ComfyUI output
        |
        v
RemixAssetItem.from_texture(path, texture_type)
        |
        v
normal conversion if needed -> DDS conversion -> metadata
        |
        v
caller uses final TextureAsset.path
```

```text
Model file (FBX/OBJ/glTF/USD)
        |
        v
RemixAssetItem.from_model(path, material_type)
        |
        v
ImporterCore standardizes to USD and materializes embedded textures
        |
        v
triangulate meshes -> convert materials to AperturePBR
        |
        v
collect TextureAsset + TextureBinding records from shader inputs
        |
        v
normal conversion -> DDS conversion -> update USD texture asset paths -> metadata
```

## Job Queue Boundary

```text
Product workflow
        |
        | binds TextureProcessingRequest
        | (items + source_root + output_url)
        v
+-----------------------------+
| TextureProcessingJob        |
| input: SOURCE_TEXTURES      |
| output: PROCESSED_TEXTURES  |
| immutable result only after |
| full pipeline success       |
+-------------+---------------+
              |
              v
+-----------------------------+
| Job Queue                   |
| async execution             |
| dependencies / fan-out      |
| may run pipelines in        |
| parallel                    |
+-------------+---------------+
              |
              | runs one isolated linear pipeline per job
              v
+-----------------------------+
| Remix asset pipeline        |
| no branching                |
| no graph ownership          |
| no shader apply/unapply     |
| one ingestion USD context   |
| per pipeline context        |
+-----------------------------+
```

The queue job accepts textures only. Future model or mesh queue jobs reuse the
same underlying Remix asset pipeline through their own exact typed contracts and
scheduler lanes. The pipeline itself remains linear.

## Application Boundary

File conversion steps are forward-only, idempotent, and safe to rerun. They do
not implement revert.

ComfyUI application is outside this extension:

```text
ComfyUI job output
        |
        v
asset pipeline processes image file
        |
        v
ComfyUI apply handler validates the live stage and assigns the processed texture
```

The pipeline exposes no apply, unapply, or revert surface. Lossy steps such as
DDS compression cannot restore the original image from the compressed output.

`TextureProcessingItem.key` is caller-defined and unique within one request. The
same key appears on `ProcessedTexture`, so downstream consumers correlate outputs
without relying on filenames or final texture semantics. This matters for normal
maps because processing changes DirectX/OpenGL semantics to octahedral normals.

Queue graphs may bind `TextureProcessingJob.SOURCE_TEXTURES` to a literal
`TextureProcessingRequest` or connect another job's exact `TextureProcessingRequest`
output. `TextureProcessingJob` uses the same `JobInputs` mapping for both paths and
returns one immutable `TextureProcessingResult` on
`TextureProcessingJob.PROCESSED_TEXTURES`. It has no product-specific Apply handler
or ComfyUI dependency.

## Design Requirements

| Requirement | Required design response |
| --- | --- |
| Avoid performance regressions from file-based processing | Reuse one isolated ingestion USD context per `RemixAssetPipelineContext`. Adjacent model steps share the cached current stage instead of creating contexts or cold-opening stages one after another. Keep this per pipeline run so parallel jobs do not share mutable USD state. |
| Do not disturb the interactive stage | Steps must not use `Usd.Stage.Open()` directly or the app's default USD context. Full-stage reads/writes go through `RemixAssetPipelineContext`, which owns a uniquely named ingestion-only context and runner cleanup. |
| Keep revert/state tracking honest | Pipeline step state records ran/skipped/error status only. File conversions do not store rollback history. Live-stage application is implemented explicitly by its owning caller. |
| Clean temporary files without step boilerplate | Steps ask `RemixAssetPipelineContext` for collision-safe workspace paths and write purposeful outputs there. The runner publishes only final referenced files plus matching `.meta` sidecars, deduplicates final names when needed, then deletes the temporary workspace. |
| Prefer shared utilities over plugins | Common texture, triangulation, and material conversion logic should be shared functions/core utilities, not new plugin abstractions unless multiple implementations are truly needed. |
| Put hard reasoning at authoring time | The canonical builder owns ordering. `validate_pipeline()` catches type/config/order problems before mutation. `should_run()` only answers whether a valid step has no work left. |
| Keep Flux generic and Lightspeed concrete | Flux owns base item/context/step/validation/execution-state classes. Remix item types, configuration, and concrete steps live here. |
| Use one stable item type | Every concrete step accepts `RemixAssetItem`. Steps mutate `TextureAsset` and `TextureBinding` records, not the item type. |
| Support model textures cleanly | Model import must materialize embedded textures as readable files, then represent them as normal `TextureAsset` records with `TextureBinding` rewrite state. |
| Do not guess material type | Model callers must provide `MaterialType.OPAQUE` or `MaterialType.TRANSLUCENT` on the model item. The pipeline maps that semantic material type to the concrete AperturePBR shader. If a caller wants old heuristic behavior, it owns that guess before calling the pipeline. |
| Avoid unstructured metadata growth | Do not add generic metadata dictionaries for pipeline contracts. Add explicit typed fields or typed context objects. |
| Validate instead of silently skipping | Wrong item/context types fail validation. Missing required model outputs, unresolved texture paths, or unsupported material conversions must fail clearly. |
| Keep steps idempotent | Re-running a step should converge: reuse existing DDS output, leave already-OTH normals alone, and rewrite metadata deterministically. |
| Keep Kit responsive without moving USD work | Pipeline steps remain sequential on Kit's event loop. Large input copies, hashing, normal conversion, DDS conversion, and transactional publication use the shared cancellation-safe worker helper. USD work and extension operations stay sequential on Kit's thread. |
| Configure steps explicitly | Use mandatory constructor arguments through `RemixAssetPipelineConfig` or explicit step constructors. Do not auto-discover schemas or auto-generate UIs for steps. |
| Keep the pipeline linear | Branching, fan-out, dependencies, and synchronization belong to the job queue or higher-level orchestration. |
| Keep the scope Remix-specific | Base abstractions are reusable through Flux, but concrete asset processing behavior is not a generic product framework. |

## Usage

```python
import pathlib

from omni.flux.asset_importer.core.data_models import TextureTypes
from lightspeed.trex.asset_pipeline.core import (
    RemixAssetItem,
    RemixAssetPipelineConfig,
    RemixAssetPipelineContext,
    run_remix_asset_pipeline,
)

item = RemixAssetItem.from_texture(pathlib.Path("/outputs/normal.png"), TextureTypes.NORMAL_DX)
context = RemixAssetPipelineContext(items=[item])
config = RemixAssetPipelineConfig(
    output_dir=pathlib.Path("/project/processed_textures"),
    texture_type=TextureTypes.NORMAL_DX,
)

await run_remix_asset_pipeline(config, context)

processed_texture = item.textures[0].path
```

```python
import pathlib

from lightspeed.trex.asset_pipeline.core import MaterialType, RemixAssetItem

item = RemixAssetItem.from_model(pathlib.Path("/assets/chair.fbx"), MaterialType.OPAQUE)
# The canonical pipeline standardizes to USD, collects referenced/materialized
# textures, processes those textures, and updates the USD texture references.
```
