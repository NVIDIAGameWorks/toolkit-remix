# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.2.0]
### Added
- Added the Remix texture and mesh pipelines as typed job-queue graphs, published lineage, a public `metadata` module, default Apply handlers, and e2e tests that prove legacy-ingested fixtures are named, hashed, and reused as the retired validator did; the collect/update/metadata steps and stage cache are replaced by texture discovery, texture application, and an async pooled USD context lease.
- Added `add_asset_optimization_jobs` to append the Prepare, texture, and mesh optimization jobs to an existing graph from a request or an upstream output.

### Changed
- Matched the legacy output contract: `<stem>.usd` with `./textures/<stem>.<letter>.rtex.dds` beside it, legacy-only sidecar keys with `src_hash`-based DDS reuse, no triangulation; removed the texture job's shared-conversion grouping and consolidated loose helpers into `utils`, `RemixAssetPipelineContext.textures`, `TextureAsset.source_path`, and `omni.flux.utils.common.path_utils.get_local_path`.
- Derived each model material target from its authored shader identifier and removed the caller-selected `MaterialType`; `MeshOptimizationRequest.output_url` now selects a local or remote destination, and the mesh job publishes the complete optimized directory there.
- Let the metadata helpers read and write sidecars for remote URLs, capture a rollback receipt before each Apply, and restore every prior sidecar when a later write fails; create missing remote parent directories before publication.

## [1.1.2]
### Changed
- DDS conversion now calls `omni.flux.nvtt.core.encode_dds` directly with typed `BlockFormat`, `gamma_encoded`, and
  `MipmapFilter` settings derived from `TextureInfo`, instead of starting one `nvtt_export` subprocess per texture.

## [1.1.1]
### Fixed
- Fixed the end-to-end progress test to observe each committed targeted progress notification.

## [1.1.0]
### Added
- Added a reusable typed texture-processing job with asynchronous progress, immutable results, explicit codecs, source-relative semantic output paths, direct USD shader metadata, and transactional local or remote publication.

### Fixed
- Preserved normal-map convention and collected USD dependency identity in stable published texture paths.
- Kept project-independent texture outputs in their durable queue job directory when no publication URL is supplied.

## [1.0.0]
### Added
- Created the Remix asset pipeline foundation with a stable asset item, texture conversion steps, metadata sidecars, canonical step ordering, unit coverage, and high-level README architecture diagrams.
