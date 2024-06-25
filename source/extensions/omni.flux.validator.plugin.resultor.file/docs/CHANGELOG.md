# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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