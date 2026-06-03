# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.5.4]
### Fixed
- Kept packaging progress responsive and cancellable until cleanup while flattening, exporting, saving repairs, and retrying unresolved-reference repairs, deleted existing package output under non-cancellable progress, disabled unsafe USDA output for flattened packages, and updated the packaging mode and output format dropdowns to expose only supported choices with Flatten as the default.

## [1.5.3]
### Fixed
- Added flatten packaging e2e regressions for missing-reference ignore, remove, replace, scan-directory, cancel, save, and completion flows.

## [1.5.2]
### Fixed
- Block packaging for projects without a valid mod layer, stop flatten-mode retries when unresolved reference errors are ignored, and keep cancellation cleanup visible with cancel disabled.

## [1.5.1]
### Changed
- Improved disabled Package Mod sidebar tooltip copy.

## [1.5.0]
### Added
- Added an RTX IO packaging section to the packaging panel for post-packaging compression and packaged DDS cleanup.
- Added RTX IO split-size presets from `1 GB` through `16 GB`.

## [1.4.9]
### Changed
- Added packaging option dropdowns for packaging mode and packaged root output extension, and open the created package directory after successful packaging.

## [1.4.6]
### Changed
- Update call sites to use renamed `LayerManagerCore` API: `get_layer_of_type()` and `get_layers_of_type()` (was `get_layer()` / `get_layers()`)

## [1.4.5]
### Changed
- Applied new lint rules

## [1.4.4]
### Changed
- Modernize python style and enable more ruff checks

## [1.4.3]
### Changed
- Switched to ruff for linting and formatting

## [1.4.2]
### Changed
- Replaced decorator-based visibility filtering with subscription lifecycle management

## [1.4.1]
### Changed
- Code formatting improvements

## [1.4.0]
### Added
- Added WorkspaceWidget interface implementation
- Added skip_when_widget_is_invisible decorator for performance optimization
- Added unit tests for visibility filtering

### Changed
- Renamed the extension to lightspeed.trex.packaging.widget

### Fixed
- Fixed workspace layout loading race condition on first load

## [1.3.1]
### Changed
- Updated popup imports to use unified omni.flux.utils.dialog extension

## [1.3.0]
### Added
- Added workspace integration for dockable Mod Packaging window
- Added sidebar integration with layout switching and stage-based button states

### Changed
- Updated UI styling and spacing for workspace layout

## [1.2.2]
### Changed
- Adjusted spacing for the new vertical modding tabs

## [1.2.1]
### Fixed
- Fixed Test assets to large to work without LFS

## [1.2.0]
### Changed
- Update the documentation for Pydantic V2 compatbility

## [1.1.0]
### Added
- Added a window to fix unresolved references

## [1.0.4]
### Changed
- Changed repo link

## [1.0.3]
- Use updated `lightspeed.layer_manager.core` extension

## [1.0.2]
### Changed
- Update to Kit 106

## [1.0.1]
### Changed
- Set Apache 2 license headers

## [1.0.0] - 2023-05-05
### Added
- Init commit.
