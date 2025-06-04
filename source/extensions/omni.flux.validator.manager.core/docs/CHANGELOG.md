# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.1.2]
## Changed
- Fix tests to run in etm context

## [2.1.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [2.1.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [2.0.0]
## Changed
- Updated Pydantic to V2

## [1.17.13]
## Changed
- Update to Kit 106.5

## [1.17.12]
## Changed
- update to use omni.kit.test public api

## [1.17.11]
### Fixed
- Fixed tests flakiness

## [1.17.10]
### Fixed
- Fixed hot-reload by allowing reuse of the validators

## [1.17.9]
### Changed
- Update deps

## [1.17.8]
### Changed
- Update deps

## [1.17.7]
### Changed
- Update deps

## [1.17.6]
### Changed
- Fixed progress bar for ingestion

## [1.17.5]
### Changed
- Update deps

## [1.17.4]
### Changed
- Update deps

## [1.17.3]
### Changed
- Update deps

## [1.17.2]
### Changed
- Update deps

## [1.17.1]
### Changed
- Update deps

## [1.17.0]
### Changed
- Renamed `_post_request` to `__send_service_request`
- Allow setting a prefix for the service endpoint using `/exts/omni.flux.validator.mass.service/service/prefix`
- Get the exception message from the HTTP Response Code

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
### Added
- Added queue id arg to be able to track what queue to update from multiple processes

## [1.15.4]
### Changed
- Set Apache 2 license headers

## [1.15.3] - 2024-04-05
### Fixed
- Fixed linting error

## [1.15.3]
### Changed
- Update deps

## [1.15.2]
### Changed
- Update deps

## [1.15.1]
### Changed
- Update deps

## [1.15.0] - 2024-03-08
### Changed
- Add more folder paths to find extensions

## [1.14.0] - 2024-02-15
### Added
- Added `_post_request` function to send update to the micro service
- Added `update` function to update the current schema
### Changed
- Changing some values of the schema will trigger automatically some events
  (like progress, finish, etc etc)

## [1.13.7]
### Changed
- Update deps

## [1.13.6]
### Changed
- Update deps

## [1.13.5]
### Changed
- Update deps

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

## [1.13.0]
### Added
- Add a flag to pass extra args to Kit for the CLI
### Changed
- Switch `check_call` to `Popen` to not have deadlock from the stdout piping.

## [1.12.5]
### Changed
- Update deps

## [1.12.4]
### Changed
- Update deps

## [1.12.3] - 2023-12-08
### Changed
- Re-enabled fastImporter

## [1.12.2]
### Changed
- Update deps

## [1.12.1]
### Changed
- Update deps

## [1.12.0]
### Added
- Call `on_crash()` when any plugin crash
- Add json decoder for the schema
- Add silent feature to silent the logger
- Set a setting `is_flux_cli` when the CLI runs

## [1.11.3]
### Changed
- Update deps

## [1.11.2]
### Changed
- Update deps

## [1.11.1]
### Changed
- Update deps

## [1.11.0]
### Added
- Added `is_ready_to_run` event

## [1.10.1]
### Added
- Optimize code to go over each plugin in a procedural way

## [1.10.0] - 2023-09-13
### Changed
- Update Kit SDK

## [1.9.5]
### Changed
- Update deps

## [1.9.4]
### Changed
- Update deps

## [1.9.3]
### Changed
- Update deps

## [1.9.2]
### Changed
- Update deps

## [1.9.1]
### Changed
- Update deps

## [1.9.0] - 2023-08-28
### Added
- Schema(s) have a `name` attribute

## [1.8.0] - 2023-08-18
### Changed
- Update deps

## [1.7.2] - 2023-08-04
### Added
- Update

## [1.7.1] - 2023-08-02
### Added
- Update

## [1.7.0] - 2023-07-19
### Added
- Update

## [1.6.0] - 2023-06-23
### Added
- Update

## [1.5.0] - 2023-06-23
### Added
- Update

## [1.4.0] - 2023-05-23
### Changed
- Dependency update

## [1.3.2] - 2023-05-10
### Fixed
- Fix for 105

## [1.3.1] - 2023-03-28
### Fixed
- Enabled registry to fix tests.

## [1.3.0] - 2023-03-20
### Added
- Add new event subscription: `on_run_started`, `on_run_paused`, `on_run_stopped`
- Plugin can control the validation (re-run or enable/disable)
- Validation can be paused/resumed

### Fixed
- Fix new packman path

## [1.2.0] - 2023-03-08
### Changed
- Use a centralized extension for Python dependencies

## [1.1.1] - 2023-02-27
### Changed
- Typo

## [1.1.0] - 2023-02-08
### Changed
- Use `omni.flux.utils.common.path_utils` for the CLI to read the json

### Added
- Reset progress of all plugins when we run

## [1.0.0] - 2023-01-26
### Added
- Init commit.
