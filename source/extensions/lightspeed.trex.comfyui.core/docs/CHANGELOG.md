# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [3.0.8]
### Fixed
- Restricted ComfyUI texture choices to mapped material inputs and excluded Other.

## [3.0.7]
### Added
- Added output-driven texture and mesh workflows with metadata sidecars, atomic Apply, Reapply, and Revert, mesh input Reference Selection and All Meshes, and a generation, preparation, texture optimization, and mesh optimization chain that publishes standalone texture outputs beside the optimized model; mesh outputs default to Replace, so every selected reference gets its own job and is replaced in place by its upscaled model; generated models use shared `Setup` commands and per-job Remix reference children, viewport instance selections target the mesh prototype, unselected references survive Replace, Undo, Revert, and Reapply, and ComfyUI node errors are reported directly.
- Added `WorkflowOutput.name` and `WorkflowOutput.group`, the export name and group typed in ComfyUI, and `Workflow.output_group_order` from the workflow's `outputGroupOrder`; all are parsed from the exported metadata and persisted (released records decode with empty values).
- Named each job graph by the workflow display name only. The preset state no longer appears in the job queue name.
- Selected Mesh inputs default to Reference Selection **Selected**, so only the reference that composes the picked prim is processed. All Meshes still defaults to **All**.
- Persisted the workflow display name, description, and type with each queued job, so a workflow reopened from the job queue names its new job graphs by display name, not by file name.

### Fixed
- Preserved reference order through Replace and Revert, included native USD input dependencies, and indexed restored source children once per owner.
- Kept Replace jobs independent on one owner and indexed source references, replacement owners, and model composition paths.
- A mesh Replace no longer captures texture targets on a material inside the replaced source model. That material is gone after Apply, so Apply failed with "The prim path does not exist in the current stage".
- Preserved external reference edits during Revert, selected models through sublayers, and isolated command registration in lifecycle tests.
- Preserved source reference metadata edits during Apply, selected nested model references, cached mesh owner discovery, and tested resolver and execution-error guards.

## [3.0.5]
### Fixed
- Wrote metadata sidecars for processed textures before replacing shader inputs, recording the pipeline's real `validation_passed` outcome, and restored them on Revert, so a texture's metadata always matches its current applied state. Separately, imported the asset pipeline job modules from their current location and the metadata sidecar helpers from the asset pipeline's `metadata` module, so the extension starts instead of failing to load.

## [3.0.4]
### Added
- Returned typed `Workflow` entries from discovery, with the display name, description, and server-defined type of each
  catalog workflow preserved on a loaded workflow.
- Added the workflow type category map (`Generation`, `Upscaling`, `Miscellaneous`, `Other`) that mirrors the node
  pack vocabulary.
- Parsed the `workflows/types` endpoint into ordered categories, each type carrying the description the server
  publishes.

## [3.0.3]
### Added
- Published stage visibility changes from each ComfyUI core's injected USD context for presentation consumers.
- Retained technical details from the current failed connection attempt for in-app diagnosis.

### Changed
- Added submitted and opened root-layer identifiers to project mismatch guidance.
- Rebuilt ComfyUI around context-bound typed workflow graphs, durable generation and texture-processing jobs, exact-project Apply validation, endpoint retargeting, explicit persistence codecs, and rollback-safe extension ownership.
- Added factory-backed typed getters, including one All Textures getter with texture and introducing-layer filters plus editable parameter guidance.
- Prepared material graphs off the UI thread with cancellable progress, detached workflow and endpoint snapshots, single-pass stage resolution, and one atomic queue transaction for the complete submission.
- Removed the obsolete queue submission and Apply-handler contract.
- Updated queue submission and apply-handler registration to use the centralized job queue runtime.
- Moved ComfyUI workflow, settings, apply, and prim traversal ownership into core with durable, context-bound artifact application.

### Fixed
- Reset workflow inputs to their defaults before applying preset overrides.
- Initialized Constant getters from USD type defaults and blocked submission when a file input is empty or unreadable.
- Preserved current getter values omitted by presets, honored explicit preset values, used durable queue-owned output for anonymous stages, and retained ComfyUI codecs until queue shutdown.

## [1.1.3]
### Changed
- Updated extension metadata for Kit SDK 110 compatibility.

## [1.1.2]
### Changed
- Modernize python style and enable more ruff checks

## [1.1.1]
### Changed
- Switched to ruff for linting and formatting

## [1.1.0]
### Added
- Added ability to add selected textures and meshes to the ComfyUI queue

### Changed
- Improved the states labels

## [1.0.0]
### Added
- Created
