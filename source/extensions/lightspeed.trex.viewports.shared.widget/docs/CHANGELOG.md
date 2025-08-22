# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.5.0]
## Changed
- Added particle gizmo layer

## [1.4.1]
## Fixed
- NoneType error when changing viewport camera speed using the mouse scroll wheel

## [1.4.0]
## Changed
- Grab updates from omni.kit.viewport.window changes

## [1.3.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [1.3.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [1.2.11]
## Changed
- Update variables and resource locations for extension testing matrix (ETM) compliance

## [1.2.10]
## Changed
- Update to Kit 106.5

## [1.2.9]
### Fixed
- Fixed tests flakiness

## [1.2.8] - 2024-07-17
### Changed
- Updated test file path

## [1.2.7]
### Changed
- Changed repo link

## [1.2.6]
### Added
- Add light manipulator layer

### Fixed
- Expose `get_active_viewport` in modules root
- Fix bug with `find_viewport_layer`

## [1.2.5]
### Changed
- Update to Kit 106

## [1.2.4]
### Fixed
- Fix Teleport tool to act on prototype relative to current instance's world position.

## [1.2.3]
### Changed
- Set Apache 2 license headers

## [1.2.2] - 2024-03-13
### Changed
- Moved e2e test to its own directory

## [1.2.1] - 2024-03-05
### Changed
- Changed the merge config reference for the mdl path for tests
- Now the `.kit` within `trex.app.resources` is referenced

## [1.2.0] - 2023-12-11
### Added
- Expose `get_viewport_api()`
- New "Teleport" Tool (Ctrl+T or Toolbar button)

## [1.1.0] - 2023-12-11
### Changed
- Expose viewport layer instances
- Remove legacy light gizmo

## [1.0.1] - 2023-11-29
### Changed
- Shared viewport will be deactivated until clicked on
- Only one shared viewport will be active at a time in order to be compliant with hydra render delegate (OM-114082)

## [1.0.0]
### Added
- Created
