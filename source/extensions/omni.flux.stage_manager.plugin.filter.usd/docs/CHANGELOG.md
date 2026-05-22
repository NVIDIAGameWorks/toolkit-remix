# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.9.1]
### Added
- Added automatic Prim Path matching before regex evaluation for path-like Stage Manager Search terms

### Changed
- Added hyphenated option descriptions to Stage Manager visibility filter tooltips
- Optimized Stage Manager Search filtering with precomputed regex state and literal matching
- Documented the `filter_active` model field for Stage Manager filters
- Included `filter_active` in filter serialization so Additional Filters can inspect modified state
- Updated USD Stage Manager filters to share `filter_active` refresh wiring

### Fixed
- Fixed Additional Filters counting hidden filter UI placement as an active user filter
- Fixed empty Search, Additional Filters menu, and neutral/default USD filter predicates participating in Stage Manager filtering
- Fixed Reset All preserving hidden Additional Filters display state
- Fixed explicit Search regex escapes like `\d` not being detected as regex patterns
- Fixed direct Search filter term assignment using stale prepared match state
- Fixed Search filter initialization bypassing shared USD filter post-init state refresh

## [2.9.0]
### Added
- REMIX-5208: Added `CustomTagsFilterPlugin` and `CheckboxGroupFilterPlugin` base class with per-tag checkboxes, prim counts, cross-tab selection preservation, `FilterCategory.TAGS` support, and reusable Select All / Deselect All actions for any OR-checkbox filter group

### Fixed
- Fixed Additional Filters popup placement, overflow scrolling, and checkbox alignment for custom tag and toggleable filters

## [2.8.0]
### Removed
- Removed `GeometryPrimsFilterPlugin` — a Lightspeed-specific implementation now owns this plugin name in the `StageManagerFactory`

## [2.7.4]
### Changed
- Updated internal import paths for prim utilities

## [2.7.3]
### Fixed
- Fixed Stage Manager filter reset functionality not resetting the filter category
### Added
- Added unit tests for AdditionalFilterPlugin

## [2.7.2]
### Changed
- Updated tooltip for all toggleable filter plugins to be on the HStack
- Updated tooltips for toggleable filter plugins better match their functionality

## [2.7.1]
### Changed
- Applied new lint rules

## [2.7.0]
### Added
- Added `GeometryPrimsFilterPlugin`
- Updated `AdditionalFilterPlugin` to use enum for filter categories
- Include nickname in the search filter

## [2.6.4]
### Changed
- Modernize python style and enable more ruff checks

## [2.6.3]
### Changed
- Switched to ruff for linting and formatting

## [2.6.2]
### Changed
- Updated filter plugin comboboxes to use the correct index for combobox creation

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
