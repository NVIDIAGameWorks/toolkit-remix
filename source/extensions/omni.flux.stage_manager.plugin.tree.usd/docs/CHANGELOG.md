# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.5.0]
### Added
- Added `_build_item()` factory methods to `VirtualGroupsModel`, `LightGroupsModel`, `MaterialGroupsModel`, and derived models

### Changed
- Updated all group models (`LightGroupsModel`, `MaterialGroupsModel`, `VirtualGroupsModel`, etc.) to use `_build_item()` for item creation
- Replaced `add_child()` calls with direct `parent` property assignment throughout

## [2.4.1]
### Changed
- Switched to ruff for linting and formatting

## [2.4.0]
## Added
- Added a nickname attribute to the tree items

## [2.3.1]
### Changed
- Updated to use centralized `get_prim_type_icons()` from `omni.flux.utils.common`

## [2.3.0]
## Added
- Added icon support for prims tab

## [2.2.0]
## Added
- Support for context menu

## [2.1.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [2.1.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [2.0.0]
## Changed
- Updated Pydantic to V2

## [1.11.1]
- Made Lights Groups Tree Plugin items icons more consistent with the other tree items

## [1.11.0]
- Added alphabetical sorting for the tree items

## [1.10.0]
- Added `MaterialGroupsTreePlugin` plugin
- Added matching `MaterialGroupsItem`, `MaterialGroupsModel`, `MaterialGroupsDelegate` classes

## [1.9.2]
## Changed
- Apply new display name style to lights tab

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
