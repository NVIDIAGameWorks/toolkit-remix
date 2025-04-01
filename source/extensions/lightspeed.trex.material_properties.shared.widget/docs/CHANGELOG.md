# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.4.1]
### Fixed
- Fixed `refresh()` to function to account for instance prims

## [1.4.0]
### Changed
- Changed `refresh()` to function based off of USD stage selection instead of Selection Tree
- Removed Selection Tree logic and connections from e2e tests

## [1.3.21]
## Changed
- Set the column widths and allow resizing

## [1.3.20]
## Changed
- added mdl file display label

## [1.3.19]
## Changed
- Update to Kit 106.5

## [1.3.18]
### Fixed
- Fixed `Assign Texture Sets` button layout

## [1.3.17]
## Changed
- update to use omni.kit.test public api

## [1.3.16]
### Fixed
- Fixed tests flakiness

## [1.3.15]
### Fixed
- Texture set search updates

## [1.3.14]
### Changed
- Clarified naming

## [1.3.13]
### Fixed
- Fixing texture set assignment

## [1.3.12]
### Added
- Added support for multi-edit

## [1.3.11] - 2024-08-06
### Changed
- External asset checker and importer

### Fixed
- Improved flakiness of copy menu tests

## [1.3.10] - 2024-07-25
### Added
- Texture string field tooltip tests

## [1.3.9] - 2024-07-15
### Added
- Right-click copy menu for current material label

## [1.3.8]
### Changed
- Updated to use centralized texture set logic

## [1.3.7]
### Changed
- Changed repo link

## [1.3.6]
- Use updated `TEXTURE_TYPE_CONVERTED_SUFFIX_MAP`

## [1.3.5] - 2024-06-05
### Changed
- File extension check now uses `get_invalid_extensions()`

### Fixed
- Drag and drop texture naming

## [1.3.4]
- Use updated `lightspeed.layer_manager.core` extension
- Use centralized TextureTypes and associated maps

## [1.3.3]
### Changed
- Update to Kit 106

## [1.3.2] - 2024-04-15
### Changed
- REMIX-2674: Adding a check for similar textures and auto-populating texture fields

## [1.3.1] - 2024-04-15
### Changed
- Updated drag and drop regex to be case-insensitive and multi-texture dialog

## [1.3.0] - 2024-04-02
### Changed
- Update to use new `FieldBuilder` to configure widgets for `MaterialPropertyWidget`

## [1.2.2]
### Changed
- Set Apache 2 license headers

## [1.2.1] - 2024-04-03
### Changed
- Update tests to account for new none frame

## [1.2.0] - 2024-03-07
### Added
- Added feature for dragging and dropping textures

## [1.1.2] - 2024-03-17
### Changed
- Update tests to account for new Other material group

## [1.1.1] - 2024-03-13
### Changed
- Moved e2e test to its own directory

## [1.1.0] - 2024-01-13
### Changed
- Override asset path file extension options to only allow DDS files

## [1.0.2] - 2023-09-29
### Fixed
- Convert shared material target should not be able to convert to current type

## [1.0.1] - 2022-08-10
### Fixed
- Fix support for convert materials on non captured prims
- Multi material selection (make clear to user that not supported)

## [1.0.0] - 2022-06-09
### Added
- Created
