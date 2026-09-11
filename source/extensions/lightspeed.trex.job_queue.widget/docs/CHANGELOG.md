# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
