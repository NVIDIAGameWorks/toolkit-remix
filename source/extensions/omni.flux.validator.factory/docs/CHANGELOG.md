# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [3.1.2]
### Changed
- Switched to ruff for linting and formatting

## [3.1.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [3.1.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [3.0.0]
## Changed
- Updated Pydantic to V2

## [2.8.0]
## Added
- Added `show` function in the base class and interface that can be called by the parent widget

## [2.7.3]
## Changed
- update to use omni.kit.test public api

## [2.7.2]
### Fixed
- Fixed tests flakiness

## [2.7.1]
### Changed
- Update deps

## [2.7.0]
### Added
- Added constants for fixed files

## [2.6.0]
### Changed
- Moved `_get_schema_data_flows` function to `Base` class

## [2.5.0]
### Changed
- Centralize `_get_schema_data_flows` function in `ResultorBase`

## [2.4.2]
### Changed
- Update deps

## [2.4.1]
### Changed
- Set Apache 2 license headers

## [2.4.0] - 2024-02-15
### Added
- Added `uuid` in the schema
### Changed
- Changing some values of the schema will trigger automatically some events
  (like progress, global progress, etc etc)

## [2.3.0] - 2023-12-06
### Added
- `on_crash()`: called when any plugin crash
### Fixed
- Fix for cloud asset(s)

## [2.2.0] - 2023-11-02
### Added
- Add `on_validation_is_ready_to_run` event

## [2.1.0] - 2023-10-23
### Added
- Added `resultor_plugins` for check and context plugin
- Add `channel` for any data
- Add utils function to centralize pushing input file into data flow

## [2.0.0] - 2023-10-12
### Change
- Changed the signature for the `on_mass_cook_template` event

## [1.7.0] - 2023-09-22
### Added
- Add `validation_extensions` constant

## [1.6.0] - 2023-08-28
### Added
- Add `hide_context_ui` in base context
- Sub context inherited parent context
- Add Mass features

## [1.5.0] - 2023-05-25
### Added
- Add `DataFlow` feature
- Add `input_data` and `output_data` for context and check plugin

## [1.4.0] - 2023-03-20
### Added
- Add validation run mode: be able to run specific plugin, etc etc
- Plugin(s) can re-run the validation with a run mode
- Plugin(s) can enable/disable the validation

## [1.3.0] - 2023-03-09
### Added
- Add display names for plugins

## [1.2.0] - 2023-03-08
### Changed
- Use a centralized extension for Python dependencies

## [1.1.0] - 2023-02-01
### Added
- Add progress subscription inside base plugin

## [1.0.0] - 2023-01-26
### Added
- Init commit.
