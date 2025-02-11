# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.9.1]
## Changed
- Apply new display name style to skeleton tab

## [1.9.0]
## Added
- Added `CustomTagGroupsTreePlugin` and related classes

## Changed
- Changed the VirtualTree item class to display virtual groups using a specific style

## [1.8.0]
## Changed
- All USD Tree Models now get a `context_name` in their constructor

## [1.7.0]
## Added
- Added a skeleton tree plugin

## [1.6.1]
### Fixed
- Fixed tests flakiness

## [1.6.0]
### Changed
- Make set_context_name() an explicit method for plugins

## [1.5.0]
### Changed
- Use the updated `context_data` data structure and filter utils function

## [1.4.1]
### Fixed
- Added missing `is_virtual` property in the `VirtualGroupsItem` class

## [1.4.0]
### Changed
- Use updated refresh logic and `build_items` & `build_item` methods to build the tree on refresh

## [1.3.2]
### Changed
- Display light type icons for every item

## [1.3.1]
### Fixed
- Clear the items on refresh before re-adding new items

## [1.3.0]
### Added
- Added `LightGroupsTreePlugin` plugin
- Added matching `LightGroupsItem`, `LightGroupsModel`, `LightGroupsDelegate` classes

## [1.2.0]
### Added
- Added `StageManagerUSDTreeItem`, `StageManagerUSDTreeModel` & `StageManagerUSDTreeDelegate` USD bases

## [1.1.0]
### Added
- Added the `PrimGroupsTreePlugin`

### Changed
- Implemented the added virtual function

## [1.0.0]
### Added
- Created
