# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.1.2]
### Changed
- Renamed `TextureProcessingDisplayAdapter` to `TextureOptimizationDisplayAdapter` (registry name `texture_optimization`) to match the asset pipeline's `TextureOptimizationJob`.
- The processed textures folder action opens the deepest directory that holds every texture, so textures published in sub-folders such as `textures/` and `_external/` still show the button. Before, the button was hidden unless every texture was in one folder.

### Fixed
- Released each registered display adapter when a later registration fails during startup.
- Registered `PrepareOptimizationDisplayAdapter` and `MeshOptimizationDisplayAdapter`, so the Optimization preparation and Mesh optimization stages show a source instead of "Unknown".

## [1.1.1]
### Changed
- Kept the texture display adapter compatible with the asset pipeline's `core.jobs` module paths and switched it to the shared `path_utils.get_local_path`.

## [1.1.0]
### Added
- Added texture-processing display, progress, Apply guidance, input-directory access, a processed-texture section with its own directory action, and centralized Job Queue and Job Details workspace names without duplicating graph actions.

### Fixed
- Kept the processed-output folder action visible with exact disabled guidance until one local output directory is available.

## [1.0.2]
### Fixed
- Updated the workspace to use the shared Apply executor.

## [1.0.1]
### Changed
- Bound the workspace to the shared queue and apply-handler runtime without product dependencies.

## [1.0.0]
### Added
- Added RTX Remix job queue and job details workspace windows backed by the shared Flux queue UI.
