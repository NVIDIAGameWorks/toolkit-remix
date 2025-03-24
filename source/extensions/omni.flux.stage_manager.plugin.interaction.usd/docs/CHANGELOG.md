# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.15.0]
## Changed
- Changed `usd_base.py` to use override-able `_get_selection()`

## [1.14.0]
## Added
- Added a materials interaction tab

## [1.13.0]
## Added
- Added rules to force refreshing the interaction tree

## [1.12.3]
## Fixed
- Fixed compatibility lists for all interactions

## [1.12.2]
## Added
- Added `MeshPrimsFilterPlugin` as a compatible filter

## [1.12.1]
## Added
- Allow categories interaction tab to be used

## [1.12.0]
## Added
- Added `AllTagsInteractionPlugin`

## Fixed
- Fixed compatible trees lists

## [1.11.1]
## Fixed
- Fixed minor issue with the USD Notice Listener callback

## [1.11.0]
## Added
- Added a skeleton interaction tab

## [1.10.1]
### Fixed
- Fixed tests flakiness

## [1.10.0]
### Added
- Added `filtering_rules` field for the USD interaction plugin base to guide the USD event filtering

### Changed
- Made the USD event callback smarter about refreshing the tree

## [1.9.0]
### Changed
- Make set_context_name() an explicit method for plugins

## [1.8.0]
### Changed
- Use the updated interaction plugins methods and the flat data structure
- Removed the overrides for the AllLights interaction plugin

## [1.7.2]
### Fixed
- Fixed a context filtering bug in the Lights interaction plugin

## [1.7.1]
### Changed
- Don't scroll to item on tree selection updated

## [1.7.0]
### Changed
- Use updated, centralized `_update_context_items` logic for the USD base
- Cleanup non-needed event listeners and methods
- Use updated `_update_context_items` and `_filter_context_items` functions in the All Lights interaction plugin
- Define the `tree` abstract property for the interaction plugins

## [1.6.0]
### Added
- Added `FocusInViewportActionWidgetPlugin`

## [1.5.3]
### Added
- Added auto scroll to selection functionality

## [1.5.2]
### Fixed
- Don't select all children when selecting an item
- Don't update the tree when moving the camera

## [1.5.1]
### Changed
- Use renamed `_tree_widget`

## [1.5.0]
### Changed
- Override newly added `_on_item_changed` to work asynchronously

## [1.4.1]
### Changed
- Allow `IsCaptureStateWidgetPlugin` to be used

## [1.4.0]
### Changed
- Implemented methods required to activate/deactivate interaction plugins

## [1.3.0]
### Added
- Added listener subscriptions to the USD Base
- Added selection synchronization to the USD Base

## [1.2.0]
### Added
- Add recursive traversal option in the `StageManagerUSDInteractionPlugin` base
- Add ability to get the context name from the context and propagate it down to every child plugin
- Added `AllLightsInteractionPlugin` plugin

### Changed
- Moved compatibility check from `AllPrimsInteractionPlugin` to base interaction class

## [1.1.1]
### Added
- Added `context_name` field to the USD base

### Changed
- Propagate the `context_name` field for all children plugins

### Fixed
- Fixed dependencies

## [1.1.0]
### Changed
- Added more compatible plugins for `AllPrimsInteractionPlugin`
- Check `context_filters` compatibility for `AllPrimsInteractionPlugin`

## [1.0.0]
### Added
- Created
