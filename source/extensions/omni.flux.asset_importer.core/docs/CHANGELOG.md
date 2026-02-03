# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.0.4]
### Changed
- Fix issue with scan folder list view interaction
- Fix issue with scan folder model ingestion validation

## [2.0.3]
### Changed
- Switched to ruff for linting and formatting

## [2.0.2]
## Changed
- Fix tests to run in etm context

## [2.0.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [2.0.0]
## Changed
- Updated Pydantic to V2

## [1.16.13]
## Changed
- Added case sensitive asset ext list

## [1.16.12]
## Changed
- Update to Kit 106.5

## [1.16.11]
### Fixed
- Fixed tests flakiness

## [1.16.10]
### Fixed
- Fixing scan folder dialog issues

## [1.16.9]
### Added
- Add a scan folder function

## [1.16.8]
### Fixed
- Fixed hot-reload by allowing reuse of the validators

## [1.16.7]
### Changed
- Update deps

## [1.16.6]
### Changed
- Update deps

## [1.16.5]
### Changed
- Centralizing texture set logic

## [1.16.4]
### Changed
- Update deps

## [1.16.3]
### Changed
- Update deps

## [1.16.2]
### Changed
- Update deps

## [1.16.1]
### Changed
- Update deps

## [1.16.0]
### Changed
- Changed `TEXTURE_TYPE_INPUT_MAP` to includes `inputs:` prefix

## [1.15.1]
### Changed
- Now ingestion overwrites referenced assets

## [1.15.0]
### Changed
- Centralized TextureTypes and related maps to the `data_models` module

## [1.14.4]
### Changed
- Update deps

## [1.14.3]
### Changed
- Update deps

## [1.14.2]
### Changed
- Update deps

## [1.14.1]
### Changed
- Set Apache 2 license headers

## [1.14.0]
### Changed
- Add more folder paths to find extensions

## [1.13.17]
### Changed
- Update deps

## [1.13.16]
### Changed
- Update deps

## [1.13.15]
### Changed
- Update deps

## [1.13.14]
### Changed
- Update deps

## [1.13.13]
### Changed
- Adding .jpeg to texture extension list

## [1.13.12]
### Changed
- Update deps

## [1.13.11]
### Changed
- Update deps

## [1.13.10]
### Changed
- Update deps

## [1.13.9]
### Changed
- Update deps

## [1.13.8]
### Changed
- Update deps

## [1.13.7]
### Changed
- Update deps

## [1.13.6]
### Changed
- Update deps

## [1.13.5]
### Fixed
- Destroy the collector at the end of the import

## [1.13.4]
### Changed
- Update deps

## [1.13.3]
### Changed
- Update deps

## [1.13.2]
### Changed
- Update deps

## [1.13.1]
### Changed
- Update deps

## [1.13.0] - 2023-09-13
### Changed
- Update Kit SDK

## [1.12.5]
### Changed
- Update deps

## [1.12.4]
### Changed
- Update deps

## [1.12.3]
### Changed
- Update deps

## [1.12.2]
### Changed
- Update deps

## [1.12.1]
### Changed
- Update deps

## [1.12.0] - 2023-08-28
### Changed
- Update deps

## [1.11.0] - 2023-08-18
### Changed
- Update deps

## [1.10.1] - 2023-08-04
### Fixed
- `--no-window` on the test

## [1.10.0] - 2023-08-02
### Added
- Update

## [1.9.0] - 2023-07-19
### Added
- Update

## [1.8.0] - 2023-06-23
### Added
- Update

## [1.7.0] - 2023-06-23
### Added
- Update

## [1.6.0] - 2023-06-13
### Added
- Added list of valid assets for asset importer and texture importer

### Changed
- Extracted the USD Files enum to the utils file

## [1.5.0] - 2023-05-23
### Changed
- Dependency update

## [1.4.1] - 2023-05-10
### Fixed
- Fix for 105

## [1.4.0] - 2023-03-31
### Added
- Added use of omni.tool.collect to import USD files without flattening them.

## [1.3.0] - 2023-03-24
### Added
- Added ability to select the output format from a list of known USD files formats

## [1.2.2] - 2023-03-27
### Fixed
- fixed `--help` for the command line interface

## [1.2.1] - 2023-03-14
### Changed
- Locked extension version to known working version

## [1.2.0] - 2023-03-08
### Changed
- Use a centralized extension for Python dependencies

## [1.1.0] - 2023-02-08
### Changed
- Use `omni.flux.utils.common.path_utils` to read the json file

## [1.0.0] - 2023-01-12
### Added
- Init commit.
