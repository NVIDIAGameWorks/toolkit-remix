# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.5.13]
## Changed
- Changed texture validation to use lowercase on extension check

## [2.5.12]
## Changed
- Update to Kit 106.5

## [2.5.11]
### Fixed
- Fixed tests flakiness

## [2.5.10]
### Changed
- Updating tests for scan folder button

## [2.5.9] - 2024-09-03
### Added
- Added validation dialog to ingestion drag-drop
- Added validation of directories being dropped for ingestion
### Changed
- Refactored validation code into separate `ingestion_checker.py` file

## [2.5.8]
### Added
- Adding scan folder buttons

## [2.5.7]
### Changed
- Updating with centralized texture set logic

## [2.5.6] - 2024-06-04
### Changed
- File extension check now uses `get_invalid_extensions()` for textures
- Improved the `validation_failed_callback` error message

## [2.5.5]
### Changed
- Use updated `TEXTURE_TYPE_INPUT_MAP`

## [2.5.4]
### Changed
- Use updated `TextureTypes`

## [2.5.3]
### Changed
- Update deps

## [2.5.2]
### Changed
- Set Apache 2 license headers

## [2.5.1] - 2024-01-20
### Fixed
- Fixed dpi scale

## [2.5.0] - 2023-12-14
### Added
- Add height texture support

## [2.4.0] - 2023-12-06
### Added
- Add Asset Browser

## [2.3.0] - 2023-11-02
### Added
- Added common `item`
- Centralize validity of a file
- Add a file listener that check validity of files in realtime
- Show invalid files in red
- Add item changed event

## [2.2.1] - 2023-10-19
### Fixed
- Fixed tests for Kit 105.1

## [2.2.0] - 2023-10-06
### Added
- Add DEL keybind to remove items for `FileImportListWidget` and `TextureImportListWidget`

### Changed
- Fixed Texture Type detection for files having the same name and different roots
- Fixed Texture Type detection for files with no keywords

## [2.1.0] - 2023-08-28
### Added
- Add external drag and drop

## [2.0.0] - 2023-08-16
### Changed
- Use OmniURL instead of Pathlib
- Improved REGEX expressions for auto texture detection
- Fixed "Convention" layout

### Added
- Added multi-selection for `FileImportListWidget` file picker
- Added CTRL+A to select all items for `FileImportListWidget` and `TextureImportListWidget`

## [1.4.2] - 2023-08-04
### Fixed
- `--no-window` on the test

## [1.4.1] - 2023-08-02
### Added
- Support for OTH texture import

## [1.4.0] - 2023-07-24
### Changed
- Show file name rather than full path in texture list (show path in tooltip)
- Change Diffuse -> Albedo for technical correctness
- Implement user-pref for normal convention

## [1.3.0] - 2023-05-17
### Changed
- Added filtering to the importer widgets to only allow selecting valid file types.

## [1.2.0] - 2023-05-01
### Added
- Added texture importer tests.

## [1.1.0] - 2023-04-27
### Added
- Added texture importer widget.

### Changed
- Change the asset importer scroll bar to match the texture importer.

## [1.0.0] - 2023-03-17
### Added
- Init commit.
