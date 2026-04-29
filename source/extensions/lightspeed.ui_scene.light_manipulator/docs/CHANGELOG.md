# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.2.1]
### Fixed
- Bracketed interactive light manipulator drags with the shared USD notice coalescer so deferred UI listeners flush once after release

## [1.2.0]
### Changed
- Added persistent viewport toggles for light manipulator visibility and intensity controls
- Integrated the manipulator toggles into the unified viewport Lights menu
- Kept menubar and viewport-manipulator dependencies lazy or optional so isolated tests do not load Remix startup paths
- Added direct coverage and golden images for the new manipulator visibility states

## [1.1.5]
### Changed
- Applied new lint rules

## [1.1.4]
### Changed
- Modernize python style and enable more ruff checks

## [1.1.3]
### Changed
- Switched to ruff for linting and formatting

## [1.1.2]
## Fixed
- Cleanup unnecessary calls to hdremix selection class

## [1.1.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [1.1.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [1.0.7]
## Fixed
- Fixed crash when stage is not available

## [1.0.6]
## Changed
- Update to Kit 106.5

## [1.0.5]
### Fixed
- Fixed tests flakiness

## [1.0.4]
### Added
- Added light manipulator for CylinderLight

## [1.0.3]
### Changed
- Fixed test deps

## [1.0.2]
### Added
- Added light manipulator for SphereLight

## [1.0.1]
### Fixed
- Fixed dependencies

## [1.0.0]
### Added
- Added light manipulators for RectLight, DistantLight and DiskLight
