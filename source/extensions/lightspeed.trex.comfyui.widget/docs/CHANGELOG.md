# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.1.2]
### Fixed
- Fitted the ComfyUI Setup window to the height that its panel needs, and filled a taller window with the panel,
  which keeps the Connect button at its bottom.

## [2.1.1]
### Added
- Added persistent ComfyUI connection banners with compact, right-aligned actions inline to the right of flexible
  wrapped text, verified browser opening, and a Show Logs modal with the exact endpoint and error in a selectable,
  copyable, read-only multiline field.

### Changed
- Added submitted and opened root-layer identifiers to project mismatch guidance.
- Rebuilt the context-aware Setup and Workflow UI with Managed/External modes, active presets, typed getter and Constant editors, resizable input properties, per-material submission, retargeting, and shared queue actions.
- Added parameter guidance and a cancellable preparation modal that closes before one atomic off-thread queue submission.
- Split workflow tree items, models, and delegates by responsibility.
- Updated ComfyUI widget imports to consume the explicit-context ComfyUI core singleton and enum module directly.

### Fixed
- Limited Focus in Viewport to live, effectively visible Xformable owners in the job's saved USD context
  and refreshed its availability after context-qualified visibility changes.
- Kept every graph action visible with clear disabled guidance when ComfyUI or its saved workflow is unavailable.
- Rendered empty File Constants without placeholder paths, validated them before submission, and kept getter actions correct when workflow state changes.
- Framed each saved object in the active Remix viewport, cycling one object per click without falling back to selection-only behavior.

## [1.2.5]
### Changed
- Updated extension metadata for Kit SDK 110 compatibility.

## [1.2.4]
### Changed
- Applied new lint rules

## [1.2.3]
### Changed
- Modernize python style and enable more ruff checks

## [1.2.2]
### Changed
- Switched to ruff for linting and formatting

## [1.2.1]
### Changed
- Replaced decorator-based visibility filtering with subscription lifecycle management

## [1.2.0]
### Added
- Added WorkspaceWidget interface implementation
- Added skip_when_widget_is_invisible decorator for performance optimization
- Added unit tests for visibility filtering

## [1.1.0]
### Added
- Added ability to add selected textures and meshes to the ComfyUI queue
- Added a window to display the ComfyUI UI

### Changed
- Improved the layout for a more production-ready UI

## [1.0.0]
### Added
- Created
