# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.9.0]
### Added
- Added a `USDDirectory` context plugin to iterate through all the USD files within a directory
- Added a cook template method to `USDFile`

## [2.8.2]
### Changed
- Updated with centralized texture set logic

## [2.8.1] - 2024-06-04
### Changed
- File extension check now uses `get_invalid_extensions()` for materials

## [2.8.0]
### Changed
- Allow creating output directory if non-existent for `asset_importer` and `texture_importer`

## [2.7.4]
### Changed
- Use the `omni.hydra.pxr` extension instead of `omni.hydra.rtx`
- Use the centralized TextureTypes maps

## [2.7.3]
### Changed
- Update deps

## [2.7.2]
### Changed
- Set Apache 2 license headers

## [2.7.1] - 2024-04-05
### Fixed
- Fixed an issue where read-only input files when copied in the output directory could not be overwritten/deleted by AI Tools
- Added exception handling to display errors in the UI

## [2.7.0] - 2024-02-15
### Changed
- Use the schema to hold tmp data (needed if we want to update the schema live)

## [2.6.1] - 2024-02-08
### Changed
- Revisions in spelling, wording, and grammar for Input File Paths Material Ingestion info.

## [2.6.0] - 2024-01-12
### Added
- Added `full_path_keep` and `full_path_root` for `AssetImporter` plugin

## [2.5.2] - 2023-12-08
### Changed
- Re-enabled fastImporter

## [2.5.1] - 2023-12-08
### Fixed
- Fixed tests

## [2.5.0] - 2023-12-06
### Added
- Close the stage when any plugin crash
- Set an renderer when we are in a CLI mode (to handle materials)
- Centralize stage close function

## [2.4.3] - 2023-11-27
### Fixed
- Added tooltip for materials tab in Ingest

## [2.4.2] - 2023-11-15
### Fixed
- For asset/texture importers, don't reset the list if we delete a wrong item

## [2.4.1] - 2023-10-31
### Added
- Added `error_on_texture_types` data attribute. We can force the validation to use only specific type(s) of texture

### Fixed
- Fix delete/renamed files on asset/texture importer

## [2.4.0] - 2023-11-07
### Added
- Added `close_stage_on_exit` for plugins.
- Added `close_dependency_between_round` for `DependencyIterator` plugin
- Added `ContextBaseUSD` and centralize the creation of the context

## [2.3.0] - 2023-10-23
### Changed
- Use an utils function to push data into data flow.

## [2.2.2] - 2023-10-19
### Fixed
- Fixed tests for 105.1

## [2.2.1] - 2023-10-06
### Fixed
- Fixed schema template crash when no UI is built

## [2.2.0] - 2023-08-28
### Added
- Add `create_context_if_not_exist`
### Changed
- Context is inherited

## [2.1.0] - 2023-08-25
### Added
- Added `save_on_exit` schema option to the `CurrentStage` context

## [2.0.0] - 2023-08-18
### Changed
- Use OmniURL instead of Path for `TextureImporter` and `AssetImporter`
- Fixed column width to make all columns the same size

## [1.9.4] - 2023-08-04
### Fixed
- `--no-window` on the test

## [1.9.3] - 2023-08-02
### Added
- Support for OTH texture import

## [1.9.2] - 2023-08-01
### Fixed
- Schema now correctly accepts and passes arguments from AssetConverterContext

## [1.9.1] - 2023-08-01
### Changed
- Utilize the info icon widget

## [1.9.0] - 2023-07-24
### Added
- Use multi-file selection for texture importer

## [1.8.0] - 2023-07-05
### Added
- Added extra output directory validation

## [1.7.0] - 2023-05-23
### Added
- Push `base_output_data` and `base_input_data` for some plugins

## [1.6.0] - 2023-05-01
### Added
- Added `texture_importer` tests

## [1.5.0] - 2023-04-26
### Added
- Added `texture_importer` context plugin

### Changed
- Added `asset_importer` plugin UI width to match `texture_importer`

## [1.4.0] - 2023-04-11
### Added
- added file picker for output directory, and token support for input and output paths to `asset_importer`

## [1.3.0] - 2023-03-24
### Added
- `asset_importer` plugins to import files and check the output

## [1.2.0] - 2023-03-21
### Added
- Add `DependencyIterator` plugin

## [1.1.0] - 2023-02-08
### Added
- `usd_file` plugin can handle Kit tokens


## [1.0.0] - 2023-01-26
### Added
- Init commit.
