# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.3.5]
### Changed
- Switched to ruff for linting and formatting

## [1.3.4]
### Fixed
- Fixed crash when creating new project due to incorrectly unregistering a global event

## [1.3.3]
### Changed
- Updated to use centralized event registration via lightspeed.event.events
- Renamed event from IMPORT_CAPTURE_LAYER to CAPTURE_LAYER_IMPORTED

## [1.3.2]
### Changed
- Use Flux Pip Archive instead of Kit Pip Archive

## [1.3.1]
### Fixed
- Fixed Test assets too large to work without LFS

## [1.3.0]
### Changed
- Update the documentation for Pydantic V2 compatibility

## [1.2.0]
### Removed
- Removed Upscale Core dependency

## [1.1.9]
### Changed
- Update to Kit 106.5

## [1.1.8]
### Fixed
- Fixed tests flakiness

## [1.1.7]
### Fixed
- Fix things for security

## [1.1.6]
### Fixed
- Handle the upscaling of the game icon without to have the AI repo cloned

## [1.1.5]
### Changed
- Use updated `lightspeed.layer_manager.core` extension

## [1.1.4]
### Changed
- Update to Kit 106

## [1.1.3] - 2024-05-01
### Fixed
- Fixed tests for Kit 106

## [1.1.2]
### Fixed
- Add `lightspeed.event.capture_persp_to_persp` because it needs to start before

## [1.1.1]
### Changed
- Set Apache 2 license headers

## [1.1.0] - 2023-10-10
### Changed
- import capture emit a custom global event now
- optimize `get_hashes_from_capture_layer()`
- added tests

### Fixed
- Fixed the "replaced" asset counter

## [1.0.0] - 2023-05-18
### Added
- Created
