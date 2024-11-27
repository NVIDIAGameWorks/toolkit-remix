# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.7.1]
### Fixed
- Fixed tests flakiness

## [2.7.0]
### Changed
- Refactored ItemModels to clarify relationship with base omni.ui classes
- Rename `BaseItemModel` to `_SetValueCallbackManager` to clarify responsibility. Behavior can still be modified via the model, and without needing to subclass BaseItemModel.

## [2.6.1]
### Changed
- Use generic centralized LayerTree model

## [2.6.0]
### Changed
- Use centralized LayerTree widget

## [2.5.2] - 2024-04-24
### Added
- Added tests for property widget

### Changed
- Adjusted `Item.__repr__` for easier debugging

## [2.5.1]
### Changed
- Update deps

## [2.5.0] - 2024-04-02
### Added
- Added `FieldBuilder` object used to provide the `Delegate` ways to customize UI widgets created per-item
- Added `FieldBuilderRegistry` used to assist in creating `FieldBuilder` instances
### Changed
- Update `Delegate` to optionally accept `list[FieldBuilder]` in init to customize widgets per-item
- Update `TestDelegate` to use new `FieldBuilder` for UI creation

## [2.4.4]
### Changed
- Set Apache 2 license headers

## [2.4.3] - 2024-03-25
### Changed
- Update `ItemModel` repr to improve debugging

## [2.4.2] - 2024-02-09
### Added
- Add copy/paste functionality for items within the property treeview
- Add serialization methods for `Item` and `ItemModel` to handle copy/paste serialization round trips
- Add e2e and unit tests for copy/paste functionality

### Changed
- Update TreeView selection logic for left/right clicks

## [2.4.1] - 2024-01-19
### Changed
- Keep widget focus when editing a value
- Modify how "virtual" attributes are presented

## [2.4.0] - 2023-06-01
### Added
- Pre and post callback during `set_value` for items
- Add `block_set_value()` to be able to block the `set_value()` function to be executed

### Fixed
- fix `__repr__` crash

## [2.3.2] - 2023-03-13
### Fixed
- Fixed missing key exception in the delegate

## [2.3.1] - 2023-01-13
### Fixed
- Fixed expansion being forced on unknown items

## [2.3.0] - 2023-01-13
### Added
- Added expansion state recovery on item changed

## [2.2.0] - 2022-11-01
### Changed
- Added dummy method for layer override indicators

## [2.1.0] - 2022-07-08
### Added
- Be able to set the default column widths of the tree
- Now the items can have a hierarchy
- Be able to set a "display" function (`set_display_fn()`) to display the value differently

## [2.0.0] - 2022-07-08
### Changed
- Refactor everything to use a treeview

## [1.1.0] - 2022-06-20
### Changed
- widget builder now supports multiple stages and use multiple property panels
- widget builder now supports vec2, vec4, string types

## [1.0.2] - 2022-06-13
### Changed
- destroy() implementations now use reset_default_attrs helper

## [1.0.1] - 2022-06-13
### Changed
- Fix crash when multiple property panels have a field with the same attribute name

## [1.0.0] - 2022-04-19
### Added
- Init commit.
