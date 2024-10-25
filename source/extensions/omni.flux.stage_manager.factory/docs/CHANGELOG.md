# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.0.2]
### Fixed
- Fixed the `filter_items` method from the `StageManagerUtils` that didn't use filtered children

## [2.0.1]
### Changed
- Added the ability to interaction plugins' `_update_expansion_states_deferred` method to not scroll to item on invocation

## [2.0.0]
### Added
- Introduced new `StageManagerItem` dataclass to transfer data between the context and interaction/tree/filter plugins
- Added `context_filters` to the interaction plugin
- Added a `_context_items_changed` event to the interaction plugin
- Added a 2-pass pipeline for data filtering (context filtering & user-filtering)
- Added `_build_items` and `_build_item` methods to the tree plugin to customize how items are refreshed

### Changed
- Moved `tree` definition from the schema to an abstract property in the interaction plugin
- Renamed `required_filters` to `internal_filters` in the interaction plugin
- Moved the tree refresh call to the `_context_items_changed` listener of the interaction plugin
- Simplified the alternating colors drawing logic in the interaction plugin
- Centralized the refresh logic in the tree plugin
- Filtering is now down in an upside-down manner to make sure we keep parent prims that have valid children

### Fixed
- Added missing `@omni.usd.handle_exception` decorators to the interaction plugin
- Fixed bugs hidden by the missing decorators
- Fixed circular imports due to absolute import paths

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
