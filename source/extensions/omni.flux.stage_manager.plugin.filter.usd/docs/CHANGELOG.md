# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.6.1]
### Changed
- Updated the check for filter sorting in AdditionalFilterPlugin

## [2.6.0]
### Changed
- Updated `AdditionalFilterPlugin` to have headers for the different filter types
- Added `InstanceGroupFilterPlugin` and `MeshGroupFilterPlugin`

## [2.5.0]
### Added
- Added `VisiblePrimsFilterPlugin`

## [2.4.1]
### Changed
- Changed default value for SearchFilterPlugin

## [2.4.0]
### Added
- Added a badge to the Additional Filters button to show the number of modified filters

## [2.3.0]
### Added
- Added `AdditionalFilterPlugin`
### Changed
- Updated `ToggleableUSDFilterPlugin` to not reverse value for checkbox

## [2.2.0]
### Changed
- Updating SearchFilterPlugin with regex matching for Stage Manager filtering

## [2.1.1]
### Fixed
- Fixed Test assets to large to work without LFS

## [2.1.0]
### Changed
- Update the documentation for Pydantic V2 compatbility

## [2.0.0]
### Changed
- Updated Pydantic to V2

## [1.6.0]
### Added
- Added `MaterialPrimsFilterPlugin` filter plugin

## [1.5.0]
### Added
- Added a filter for skeleton interaction tab

## [1.4.1]
### Fixed
- Fixed tests flakiness

## [1.4.0]
### Changed
- Make set_context_name() an explicit method for plugins

## [1.3.0]
### Changed
- Use updated `filter_predicate` method

## [1.2.1]
### Fixed
- Fixed EventSubscription typing

## [1.2.0]
### Added
- Added `ToggleableUSDFilterPlugin` base filter class
- Added `LightPrimsFilterPlugin` filter plugin

### Changed
- Improved `IgnorePrimsFilterPlugin` filtering

### Changed
- Refactor `OmniPrimsFilterPlugin` to inherit from `ToggleableUSDFilterPlugin`

## [1.1.1]
### Added
- Added `context_name` field to the USD base

### Fixed
- Fixed dependencies

## [1.1.0]
### Added
- Added `IgnorePrimsFilterPlugin` plugin
- Added `OmniPrimsFilterPlugin` plugin

## [1.0.0]
### Added
- Created
