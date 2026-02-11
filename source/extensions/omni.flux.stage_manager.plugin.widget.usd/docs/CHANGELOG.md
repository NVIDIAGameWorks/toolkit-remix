# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.1.5]
### Changed
- Modernize python style and enable more ruff checks

## [2.1.4]
### Changed
- Switched to ruff for linting and formatting

## [2.1.3]
## Changed
- Implemented `build_overview_ui` method in `StageManagerUIPluginBase`

## [2.1.2]
## Changed
- Exposing the custom tags list widget to work with the new context menu

## [2.1.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [2.1.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [2.0.0]
## Changed
- Updated Pydantic to V2

## [1.9.0]
### Changed
- Use newly created `SetVisibilitySelectedPrimsCommand` command to set all items to the same value instead of toggling

## [1.8.0]
### Added
- Use the new items' `build_widget` method instead of a label

## [1.7.0]
### Added
- Added `custom_tags_list` widget

## [1.6.1]
### Fixed
- Fixed tests flakiness

## [1.6.0]
### Changed
- Make set_context_name() an explicit method for plugins

## [1.5.0]
### Changed
- Use updated `item.data` data structure. The data is now the prim itself.

## [1.4.1]
### Fixed
- Gave the icon widget vertical stack a width of 0 to take only required space

## [1.4.0]
### Added
- Added `build_icon_ui` function to `StageManagerStateWidgetPlugin`

### Changed
- Changed `StageManagerStateWidgetPlugin` to center icons vertically by default.
- Changed `PrimTreeWidgetPlugin` to center icons vertically by default.
- Renamed `state_is_visible` to `action_is_visible`
- Use selection instead of item for the `action_is_visible` clicked behavior

## [1.3.2]
### Changed
- Use renamed `build_overview_ui` function

## [1.3.1]
### Changed
- Improve `PrimTreeWidgetPlugin` result text

## [1.3.0]
### Changed
- Added ability for `PrimTreeWidgetPlugin` to display icons

## [1.2.0]
### Changed
- Added `context_name` field to the USD base
- Implemented the `IsVisibleActionWidgetPlugin` plugin

### Fixed
- Fixed dependencies

## [1.1.0]
### Added
- Added `StageManagerStateWidgetPlugin` plugin base
- Added `IsVisibleActionWidgetPlugin` plugin

### Changed
- Implemented `PrimTreeWidgetPlugin` plugin

## [1.0.0]
### Added
- Created
