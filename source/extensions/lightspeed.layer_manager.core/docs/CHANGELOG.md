# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.2.8]
### Fixed
- Changed usages of the `CreateSublayer` command for `CreateOrInsertSublayer`

## [2.2.7]
### Changed
- Update to Kit 106.5

## [2.2.6]
### Fixed
- Fixed crash for new stage unloading logic

## [2.2.5]
### Changed
- update to use omni.kit.test public api

## [2.2.4]
### Fixed
- Fixed tests flakiness

## [2.2.3]
### Added
- Added a new function for layer type validation

## [2.2.2]
### Changed
- Modified `open_stage()` and `create_new_stage()` to return non-anonymous previous root layer identifiers

## [2.2.1]
### Fixed
- Fixed hot-reload by allowing reuse of the validators

## [2.2.0]
### Added
- Added new functions `broken_layers_stack` and `remove_broken_layer`

## [2.1.0]
### Added
- Added endpoint to get layer types

### Fixed
- Fixed errors with service layer functions

## [2.0.1]
### Changed
- Don't use pydantic for typing to fix documentation

## [2.0.0] - 2023-11-16
### Changed
- Renamed the extension to `lightspeed.layer_manager.core`

### Added
- Added `with_identifier` functions equivalents for existing functions
- Added `with_data_model` functions equivalents for existing functions
- Added data models representing the various requests and responses possible
- Added validators for the data models

## [1.0.3]
### Changed
- Update to Kit 106

## [1.0.2]
### Changed
- Set Apache 2 license headers

## [1.0.1] - 2023-10-10
### Fixed
- remove layer: check is the layer is expired

## [1.0.0] - 2023-06-06
### Added
- Added `get_layers` to allow getting multiple layers of a given type

## [0.1.1] - 2022-06-09
### Fixed
- fixed `_reset_default_attrs`

## [0.1.0] - 2021-11-17
### Added
- First commit
