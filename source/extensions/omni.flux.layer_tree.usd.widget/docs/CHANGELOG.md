# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.9.3]
### Fixed
- Fixed create/import layer buttons state after a refresh
- Changed usages of the `CreateSublayer` command for `CreateOrInsertSublayer`

## [1.9.2]
### Changed
- Update to Kit 106.5

## [1.9.1]
### Changed
- Persist the selection through refreshes

### Fixed
- Fixed inconsistent muteness states
- Fixed stage events not triggering refresh
- Fixed widget being interactable while loading in progress
- Catch async exceptions in the refresh function

## [1.9.0]
### Changed
- Improved UI for invalid edit targets
- Fixed refresh blocking the UI

## [1.8.3]
### Changed
- update to use omni.kit.test public api

## [1.8.2]
### Fixed
- Fixed tests flakiness

## [1.8.1]
### Changed
- Use generic centralized LayerTree model

## [1.8.0]
### Changed
- Use centralized LayerTree widget

## [1.7.5]
### Changed
- Update deps

## [1.7.4] - 2024-04-10
### Added
- Added cursor change when hovering the scrollbar

## [1.7.3]
### Changed
- Set Apache 2 license headers

## [1.7.2] - 2024-02-02
### Fixed
- Save the edit target to the project file on set

## [1.7.1] - 2023-10-13
### Fixed
- Fix crash on destroy

## [1.7.0] - 2023-05-22
### Added
- Added ability to set default expansion state and set tree height on init
- Added ability to hide create/insert buttons

## [1.6.0] - 2023-05-17
### Changed
- Use `omni.flux.layer_tree.usd.core`

## [1.5.2] - 2023-05-18
### Fixed
- Allow `test_create_new_layer` to run multiple times consecutively

## [1.5.1] - 2023-05-17
### Fixed
- Fixed ETM failure because of std_out logging

## [1.5.0] - 2023-05-04
### Added
- Added ability to read widget exclusion state from custom layer data

## [1.4.1] - 2023-03-29
### Fixed
- Fix for ETM tests

## [1.4.0] - 2023-03-06
### Added
- Added default styling to avoid crashes

### Removed
- Removed default styling from e2e tests

## [1.3.1] - 2023-03-01
### Fixed
- Fixed e2e tests

## [1.3.0] - 2023-02-21
### Added
- Added e2e tests

### Updated
- Use mouse_released_fn in the delegate instead of mouse_pressed_fn (OM-78744 fixed)

## [1.2.0] - 2023-01-17
### Added
- Added context menu on the layer delegate with utility actions

## [1.1.5] - 2023-01-13
### Fixed
- Also validate imported layers

## [1.1.4] - 2023-01-13
### Updated
- Added the ability to add a validation function to the `create_layer` function in the `LayerModel`
- Added the ability to add a validation failed callback to the `create_layer` function in the `LayerModel`

## [1.1.3] - 2022-12-08
### Updated
- Disable muting the active edit target

## [1.1.2] - 2022-12-19
### Updated
- Use USDA as a default file format when creating new layers
- Fixed titles & apply strings to be more consistent

## [1.1.1] - 2022-11-28
### Updated
- Layers can now be excluded from being moved
- Added layer identifiers to layer tooltips

## [1.1.0] - 2022-11-28
### Added
- Layers can now be re-ordered

## [1.0.6] - 2022-11-14
### Updated
- Updated icon to be more consistent with other widgets

## [1.0.5] - 2022-11-07
### Fixed
- Fixed various issues
- Only show expansion arrow when an item has children

## [1.0.4] - 2022-11-07
### Fixed
- Crash is stage doesn't exist anymore

## [1.0.3] - 2022-11-07
### Fixed
- Added disabled styles for excluded layers
- Fixed callbacks getting called with disabled buttons
- Added refresh function to update exclude lists

## [1.0.2] - 2022-11-07
### Fixed
- Extract Icons Builder function to allow overrides
- Locked layers should not be able to be edit target
- Allow lists to be given for action exclusions

## [1.0.1] - 2022-11-02
### Fixed
- Added missing extension dependency

## [1.0.0] - 2022-08-29
### Added
- Init commit.
