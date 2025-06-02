# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.1.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [2.1.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [2.0.0]
## Changed
- Updated Pydantic to V2

## [1.7.4]
## Changed
- Update to Kit 106.5

## [1.7.3]
## Changed
- update to use omni.kit.test public api

## [1.7.2]
### Fixed
- Fixed tests flakiness

## [1.7.1]
### Fixed
- Implement missing abstract methods

## [1.7.0]
### Changed
- `FileMetadataWritter` will now write file fixes for all output files

## [1.6.0]
### Added
- Added `dataflow_to_json` resultor to save dataflow contents to a JSON file

### Changed
- Use centralized `_get_schema_data_flows` functions

## [1.5.5]
### Changed
- Update deps

## [1.5.4]
### Changed
- Set Apache 2 license headers

## [1.5.3] - 2024-02-15
### Fixed
- Fix dependency

## [1.5.2] - 2023-12-08
### Changed
- Re-enabled fastImporter

## [1.5.1] - 2023-12-08
### Fixed
- Fixed tests

## [1.5.0] - 2023-12-06
### Added
- Json plugin uses schema json encoder

## [1.4.0] - 2023-10-23
### Added
- Add `FileInputCleanup` plugin

## [1.3.0] - 2023-09-22
### Added
- Add extension versions in metadata

## [1.2.2] - 2023-08-28
### Fixed
- Fix tests

## [1.2.1] - 2023-08-18
### Fixed
- Added `allow_reuse=True` to the `json_path` validator

## [1.2.0] - 2023-05-25
### Added
- Add `FileMetadataWritter` plugin

## [1.1.1] - 2023-03-28
### Fixed
- Enabled registry to fix tests.

## [1.1.0] - 2023-02-08
### Added
- Json plugin can use a path with Kit tokens to write the result

### Changed
- Use `omni.flux.utils.common.path_utils` API to write the json

## [1.0.0] - 2023-01-26
### Added
- Init commit.
