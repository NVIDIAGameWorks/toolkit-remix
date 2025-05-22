# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.8.7]
## Fixed
- fix shader_identification validator to resolve mdl path tokens

## [1.8.6]
## Changed
- Update variables and resource locations for extension testing matrix (ETM) compliance

## [1.8.5]
## Changed
- Update to Kit 106.5

## [1.8.4]
### Fixed
- Fixed tests flakiness

## [1.8.3]
### Changed
- Remove repo link (privacy)

## [1.8.2]
### Changed
- Update deps

## [1.8.1]
### Changed
- Set Apache 2 license headers

## [1.8.0] - 2024-03-08
### Changed
- Add more folder paths to find extensions

## [1.7.0] - 2024-01-12
### Changed
- Validation handle internal material nodes from USD (like `UsdPreviewSurface`)

## [1.6.0] - 2023-12-14
### Added
- Add height texture support

## [1.5.0] - 2023-12-06
### Added
- `_translate_alt()` and `_translate()` take `input_attr` as an arg
- add `fake_attribute` schema attribute
- add `USD Preview Surface` to `AperturePBR`
- handle no MDL shader

## [1.4.1] - 2023-11-03
### Fixed
- Check if output/input shader exists before conversion

## [1.4.0] - 2023-10-30
### Added
- Add OmniGlass to AperturePBR

## [1.3.7] - 2023-10-19
### Fixed
- Fixed tests for Kit 105.1

## [1.3.6] - 2023-09-08
### Fixed
- Fixed crash when no final material or shader is found

## [1.3.5] - 2023-08-24
### Added
- Aperture Translucent to the list of supported outputs.

## [1.3.4] - 2023-08-07
### Added
- Support ingesting assets with unknown materials (using a default aperture pbr)

## [1.3.3] - 2023-08-03
### Fixed
- Crash when texture fields are empty

## [1.3.2] - 2023-08-02
### Added
- Support for OTH texture import

## [1.3.1] - 2023-05-15
### Fixed
- Use `renderer.mdl.searchPaths.templates` setting for MDL paths

## [1.3.0] - 2023-04-19
### Added
- Added unit and end-to-end tests

## [1.2.0] - 2023-04-19
### Added
- Added the ability to set default output values for attributes

### Fixed
- Fixed bad output attribute name for normal encoding

## [1.1.0] - 2023-04-17
### Changed
- Changed the core to use shader subidentifiers for the output
- Added a utils method to get all shader paths as OmniURLs from the material library paths

### Fixed
- Fixed conversion errors

## [1.0.0] - 2023-03-31
### Added
- Init commit.
