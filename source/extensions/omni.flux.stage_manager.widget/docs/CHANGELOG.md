# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.6.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [1.6.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [1.5.2]
## Changed
- Removed a function to set a refresh callback

## [1.5.1]
## Added
- Added a function to set a refresh callback

## [1.5.0]
## Changed
- Removed Experimental Feature label

## [1.4.7]
## Changed
- Update to Kit 106.5

## [1.4.6]
### Changed
- Disabled the raster policy to fix refresh issues

## [1.4.5]
### Fixed
- Fixed tab padding

## [1.4.4]
### Changed
- Reduced the tab horizontal padding

## [1.4.3]
### Changed
- Changed the raster policy for the Stage Manager frame for improved performance at rest

## [1.4.2]
### Fixed
- Fixed tests flakiness

## [1.4.1]
### Added
- Added `Experimental Feature` label

## [1.4.0]
### Changed
- Made `select_tab` public & deferred
- Only set active/inactive once during the tab update process

## [1.3.1]
### Fixed
- Disable all interaction plugins on destroy to clear all listeners

## [1.3.0]
### Added
- Added `resize_tabs` function to resize the tabs

### Changed
- Made `core` an optional argument
- Added `**kwargs` arguments to pass down to the root frame

## [1.2.0]
### Changed
- Optimize the way the interaction UI is built

## [1.1.0]
### Changed
- Deactivate interaction plugins when the tab is not visible in the widget

## [1.0.1]
### Fixed
- Added `handle_exception` decorator for async functions

## [1.0.0]
### Added
- Init commit.
