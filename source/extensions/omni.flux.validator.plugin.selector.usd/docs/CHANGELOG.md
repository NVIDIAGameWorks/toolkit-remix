# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.9.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [1.9.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [1.8.5]
## Changed
- Update to Kit 106.5

## [1.8.4]
## Changed
- update to use omni.kit.test public api

## [1.8.3]
### Fixed
- Fixed tests flakiness

## [1.8.2]
### Fixed
- Fixed test plugins to implement all abstract methods

## [1.8.1]
### Fixed
- Fix `AllTextures` plugin

## [1.8.0]
### Changed
- Added the ability to select root layer prims only for all selectors using `select_from_root_layer_only`

## [1.7.4] - 2024-05-29
### Changed
- File extension check now uses `get_invalid_extensions()`

## [1.7.3]
### Changed
- Use updated TextureTypes

## [1.7.2]
### Changed
- Update deps

## [1.7.1]
### Changed
- Set Apache 2 license headers

## [1.7.0] - 2024-01-12
### Added
- Added `include_geom_subset` for `AllMeshes` plugin

## [1.6.3] - 2023-12-08
### Changed
- Re-enabled fastImporter

## [1.6.2] - 2023-12-08
### Fixed
- Fixed tests

## [1.6.1]
### Changed
- Update deps

## [1.6.0] - 2023-12-06
### Added
- Close stage on crash

## [1.5.0] - 2023-08-28
### Changed
- Use inherited context
- All prims plugin: ignore internal Kit prims

## [1.4.0] - 2023-08-25
### Added
- Added `RootPrim` selector to select all the root prims of a stage

## [1.3.1] - 2023-03-28
### Fixed
- Enabled registry to fix tests.

## [1.3.0] - 2023-03-24
### Added
- Added all shaders selector.

## [1.2.0] - 2023-02-28
### Added
- Added nothing selector.

## [1.1.1] - 2023-02-16
### Added
- Added all meshes, all materials selectors.

## [1.1.0] - 2023-02-13
### Changed
- Have tests works with the new schema

## [1.0.0] - 2023-01-26
### Added
- Init commit.
