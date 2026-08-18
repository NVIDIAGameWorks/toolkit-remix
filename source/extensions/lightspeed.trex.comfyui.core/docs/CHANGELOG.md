# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
