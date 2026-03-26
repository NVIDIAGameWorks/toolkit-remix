# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.7.0]
### Added
- Added `DELETECAPTURE` action type for deleting capture-originating meshes and lights by removing their capture reference arc
- Added a context menu on the Restore action icon with selective restore options: restore original asset or restore only the captured asset reference

## [2.6.6]
### Fixed
- Fixed `focus_in_viewport` action widget losing multiselection by removing the `_item_clicked` call and injecting pre-computed union paths into the viewport framing payload

## [2.6.5]
### Fixed
- Fixed delete failing on ancestral prims that are defined in replacement sublayers
- Fixed delete and restore not working on instanced prims by resolving to the prototype
- Fixed composition-only prims incorrectly showing an active delete icon instead of a disabled restore icon
- Fixed Stage Manager crash from expired prim access after delete or restore operations

## [2.6.4]
### Changed
- Applied new lint rules

## [2.6.3]
### Added
- Updated the nickname toggle action to be global and have a dynamic splitter

## [2.6.2]
### Changed
- Modernize python style and enable more ruff checks

## [2.6.1]
### Changed
- Switched to ruff for linting and formatting

## [2.6.0]
### Added
- Added a nickname attribute to the stage manager action widget

## [2.5.2]
### Fixed
- Fixed removed redundant get_prototype call in get_selected_by_action

## [2.5.1]
### Fixed
- Fixed console error that printed for object that do not return a prototype

## [2.5.0]
### Changed
- Updated the Stage Manager Action Widget's logic (for Restore/Delete) to correctly handle the Restore, Disable, and Delete states for a wider range of objects ("prims"). The updated logic now properly assesses the object's definition parent layer type and override state, ensuring comprehensive coverage.

## [2.4.1]
### Fixed
- Fixed logic inconstancy around what objects are valid Remix Logic Graph hosts to match logic in the attribute pannel

## [2.4.0]
### Added
- Added new Logic Graph Action Plugin to Stage Manager, which provides OmniGraph integration with right-click menus for Add Graphs, Delete Graphs, and Open Graphs for editing, plus remix logic type filtering

## [2.3.1]
### Changed
- Removed unused import

## [2.3.0]
### Added
- Added new Delete Restore Action Plugin to Stage Manager, which allows users to delete Omni Graph primitives and Restore (in mesh group XForm primitives) primitives to their original capture state

## [2.2.3]
### Changed
- Updated test configuration to exclude render product warnings

## [2.2.2]
### Fixed
- Fixed logic to enable particle system creation on prims

## [2.2.1]
### Fixed
- Fixed a bug on selection of prims compatible with particle systems

## [2.2.0]
### Added
- Added an icon for the particle system action

### Changed
- Added the ability to create particle systems on materials

## [2.1.0]
## Added
- Registering stage manager widgets in the global context menu.

## [2.0.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [2.0.0]
## Changed
- Updated Pydantic to V2

## [1.4.5]
## Added
- Added an action for categories

## [1.4.4]
## Changed
- Update to Kit 106.5

## [1.4.3]
## Fixed
- skeleton remapping tool: handle missing skeleton

## [1.4.2]
## Changed
- Changed the hidden category state tooltip

## [1.4.1]
## Added
- Added a check for hidden categories

## [1.4.0]
## Added
- Added an action to open skeleton remapping tool

## [1.3.1]
### Fixed
- Fixed tests flakiness

## [1.3.0]
### Changed
- Use set_context_name()

## [1.2.0]
### Changed
- Use updated item data structure. `item.data` is now the prim itself.

## [1.1.0]
### Added
- Added `FocusInViewportActionWidgetPlugin`
- Added E2E tests

## [1.0.2]
### Changed
- Use renamed `build_icon_ui` function

## [1.0.1]
### Changed
- Use renamed `build_overview_ui` function

## [1.0.0]
### Added
- Created
