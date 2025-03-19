# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.5.4]
## Fixed
- Fixed some validators and core functions with bugs discovered during testing

## [2.5.3]
## Changed
- rename trex prim utility names for clarity

## [2.5.2]
## Changed
- Update to Kit 106.5

## [2.5.1]
## Changed
- Fix for skel logic if not fully defined.

## [2.5.0]
## Changed
- Changed `get_default_output_directory_with_data_model` to add the ability to specify which default path to use

## [2.4.0]
## Changed
- Separated skeleton logic into its own module

## Added
- created a class to help with skel remapping operations

## [2.3.6]
## Changed
- update to use omni.kit.test public api

## [2.3.5]
### Fixed
- Fixed tests flakiness

## [2.3.4]
### Changed
- Fixed `replace_reference_with_data_model` function crash

## [2.3.3]
### Changed
- Clarified naming

## [2.3.2]
### Fixed
- Fixed `append_reference_with_data_model` function crash

## [2.3.1]
### Fixed
- Fixed `select_prim_paths_with_data_model` function crash

## [2.3.0]
### Changed
- Changed `prim_is_from_a_capture_reference` to work with any prim, not just meshes

## [2.2.0] - 2024-08-06
### Added
- Asset within project directory checker
- USD (+ metadata) copier
- Added option to not ignore invalid paths for `was_the_asset_ingested()`

## [2.1.4]
### Fixed
- Fixed hot-reload by allowing reuse of the validators

## [2.1.3]
### Added
- Added function for adding attribute

## [2.1.2]
### Changed
- Remove parent prim override if there are no changed attrs

## [2.1.1]
### Changed
- Changed repo link

## [2.1.0]
### Added
- Added ability to filter get assets on a specific layer

## [2.0.1]
### Changed
- Don't use pydantic for typing to fix documentation

## [2.0.0] - 2022-11-16
### Added
- Added `with_data_model` functions equivalents for existing functions
- Added data models representing the various requests and responses possible
- Added validators for the data models

## [1.1.4]
### Changed
- Update to Kit 106

## [1.1.3]
### Fixed
- Updated some typing

## [1.1.2]
### Changed
- Set Apache 2 license headers

## [1.1.1] - 2024-03-13
### Changed
- Moved unit test to its own directory

## [1.1.0] - 2022-08-10
### Added
- Expose some API as static

## [1.0.1] - 2022-08-08
### Added
- Support for Geometry Subsets

## [1.0.0] - 2022-06-09
### Added
- Created
