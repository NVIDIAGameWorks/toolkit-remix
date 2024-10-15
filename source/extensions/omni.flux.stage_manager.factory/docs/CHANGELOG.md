# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.6.1]
### Added
- Added auto scroll to selection functionality

## [1.6.0]
### Added
- Added the ability to left-align column titles

### Changed
- Made the background of the interaction plugin tree alternating colors
- Bubble the `_item_clicked` event in the delegate when the widgets trigger the event

## [1.5.0]
### Changed
- Refresh interaction plugin widgets on tree model item changed
- Renamed `build_result_ui` to `build_overview_ui`

## [1.4.0]
### Added
- Added the ability to deactivate interaction plugins for performance optimizations

## [1.3.0]
### Added
- Added listener plugins

### Changed
- Changed the `GENERIC` data type to `NONE`

## [1.2.0]
### Changed
- Split context plugins setup between `setup()` and `get_items()`
- Add the ability not to display filters
- Changed interactions to not have `context_filters` separate from `filters`
- Centralized compatibility check for interaction plugins
- Filter context items at the interaction-level while allowing tree models to also filter afterwards (for recursive item creation)

## [1.1.1]
### Changed
- Added the ability to set the context from the core to the interaction plugin

### Fixed
- Fixed model serialization

## [1.1.0]
### Changed
- Implemented plugin base classes

## [1.0.0]
### Added
- Created
