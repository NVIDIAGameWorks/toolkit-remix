# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.13.0]
## Added
- Implemented the show function to update widgets when they are displayed in the UI

## [1.12.2]
## Changed
- update to use omni.kit.test public api

## [1.12.1]
### Fixed
- Fixed tests flakiness

## [1.12.0] - 2024-09-18
### Added
- Added UI for the executors to enable parallel-process ingestion
- Added functionality that updates the process count for parallel-process ingestion

## [1.11.10]
### Fixed
- Fixed test plugins to implement all abstract methods

## [1.11.9]
### Changed
- Update deps

## [1.11.8]
### Changed
- Update deps

## [1.11.7]
### Changed
- Update deps

## [1.11.6]
### Changed
- Update deps

## [1.11.5]
### Changed
- Update deps

## [1.11.4]
### Changed
- Update deps

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
### Changed
- Set the endpoint prefix setting in the command
- Moved Executors enum to `data_models` module
- Added the ability to initialize the manager with a dictionary instead of a JSON file path
- Added the ability to specify the kit executable location in the CLI

## [1.10.4]
### Changed
- Update deps

## [1.10.3]
### Changed
- Update deps

## [1.10.2]
### Fixed
- Fix running of the process executor from a directory with a space

## [1.10.1]
### Changed
- Update deps

## [1.10.0]
### Added
- Added queue id arg to be able to let the process tracks another process
- Add a `standalone` kwargs. When true, more things can be done (like sending request to another process or not)

### Removed
- Remove `--send-request` arg.

## [1.9.5]
### Changed
- Update deps

## [1.9.4]
### Changed
- Set Apache 2 license headers

## [1.9.3]
### Changed
- Update deps

## [1.9.2]
### Changed
- Update deps

## [1.9.1]
### Changed
- Update deps

## [1.9.0] - 2024-03-08
### Changed
- Add more folder paths to find extensions

## [1.8.0] - 2024-02-28
### Added
- Added `_post_request` function to send update to the micro service
- Added `update` function to update the current schema
### Changed
- Changing some values of the schema will trigger automatically some events
  (like progress, finish, etc etc)

## [1.7.8]
### Changed
- Update deps

## [1.7.7]
### Changed
- Update deps

## [1.7.6]
### Changed
- Update deps

## [1.7.5]
### Changed
- Update deps

## [1.7.4]
### Changed
- Update deps

## [1.7.3]
### Changed
- Update deps

## [1.7.2]
### Changed
- Update deps

## [1.7.1]
### Changed
- Update deps

## [1.7.0]
### Added
- Add a new executor that run each job from the CLI into multiple subprocess
- Add a `executor` arg for the CLI
- Add a `timeout` arg for the CLI
### Changed
- Switch `check_call` to `Popen` to not have deadlock from the stdout piping.

## [1.6.5]
### Changed
- Update deps

## [1.6.4]
### Changed
- Update deps

## [1.6.3]
### Changed
- Update deps

## [1.6.2]
### Changed
- Update deps

## [1.6.1]
### Changed
- Update deps

## [1.6.0]
### Added
- Add silent feature to silent the logger
- Set a setting `is_flux_cli` when the CLI runs
- Fix the whole CLI
- When there are crashes, write a report in the current directory

## [1.5.3]
### Changed
- Update deps

## [1.5.2]
### Changed
- Update deps

## [1.5.1]
### Changed
- Update deps

## [1.5.0]
### Added
- Detect when `cook_template` crash from the validation

## [1.4.0]
### Added
- Add handling of resultor plugins in check plugins

## [1.3.0] - 2023-09-13
### Changed
- Update Kit SDK

## [1.2.0]
### Added
- Added ability for schema tree `Item` and `Model` to subscribe to template cooking event

## [1.1.2]
### Changed
- Update deps

### Fixed
- Fixed mass ingestion modifying cooked schemas

## [1.1.1]
### Changed
- Update deps

## [1.1.0]
### Added
- Add tests + doc

## [1.0.1]
### Changed
- Update deps

## [1.0.0] - 2023-07-28
### Added
- Init commit.
