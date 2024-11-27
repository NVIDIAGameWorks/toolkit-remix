# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
