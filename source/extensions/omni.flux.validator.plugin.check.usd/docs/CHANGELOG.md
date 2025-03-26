# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [3.14.2]
### Fixed
- Changed usages of the `CreateSublayer` command for `CreateOrInsertSublayer`

## [3.14.1]
## Changed
- Update to Kit 106.5

## [3.14.0]
## Changed
- Changed `meters_per_unit_target` for `scale_target`

## [3.13.3]
## Changed
- update to use omni.kit.test public api

## [3.13.2]
### Fixed
- Fixed tests flakiness

## [3.13.1]
### Fixed
- Fixed import order for the internal pip archive

## [3.13.0]
### Changed
- Changed `value_mapping.py` to support mapping functions on top of hardcoded input/output combos

## [3.12.0]
### Changed
- Use `omni.flux.internal_pip_archive` for remix AI libraries

## [3.11.1]
### Changed
- Use updated `___TEXTURE_TYPE_INPUT_MAP`

## [3.11.0]
### Added
- Added `__get_texture_type_suffix` function to get texture type expected suffix

### Changed
- Use centralized TextureType maps
- Move suffix config to centralized extension

## [3.10.1]
### Changed
- Update deps

## [3.10.0]
### Changed
- Load AI Library dependencies asynchronously to avoid PyTorch slowdown on startup

## [3.9.1]
### Changed
- Set Apache 2 license headers

## [3.9.0] - 2024-03-08
### Changed
- Add more folder paths to find extensions

## [3.8.0] - 2024-02-15
### Changed
- Use the schema to hold tmp data (needed if we want to update the schema live)

## [3.7.0]
### Added
- Added denoising steps and noise level in schema

### Changed
- Changed default values to take advantage of VRAM more

## [3.6.2]
### Changed
- Update deps

## [3.6.1] - 2024-02-14
### Changed
- Set the `supported_extensions` optional argument for the `GeneratePBRMaterial` plugin

## [3.6.0] - 2024-01-29
### Added
- Added ability to set OversizedBehavior from the UI. (Quick VS Quality inference)

## [3.5.1] - 2024-01-17
### Changed
- Update to work with updated client code

## [3.5.0] - 2024-01-12
### Added
- Added `ClearUnassignedMaterial` plugin
- Added `GenerateThumbnail` plugin
### Changed
- `WrapRootPrims` ignore internal Kit prims
### Fixed
- Fix deadlock from calling `load_mdl_parameters_for_prim_async()`

## [3.4.2] - 2024-01-08
### Changed
- Assume all textures are tiling for I2M

## [3.4.1] - 2023-12-20
### Added
- Updated `remix-client` to support patchwise inference
- Improve tooltip

## [3.4.0] - 2023-12-14
### Added
- Add height texture support

## [3.3.2]
### Changed
- Update deps

## [3.3.1] - 2023-12-08
### Changed
- Moved `remix-client` and `remix-models-i2m` PIP dependencies to PIP archive

## [3.3.0] - 2023-12-07
### Added
- Added `GeneratePBRMaterial` plugin for AI PBR Material generation
- Added PIP dependencies required to execute the `GeneratePBRMaterial` plugin

## [3.2.0] - 2023-12-06
### Added
- Close the current stage when any plugin crash
- Don't create materials for empty meshes
- Add `replace_udim_textures_by_empty` feature

## [3.1.0] - 2023-10-23
### Added
- Added `ignore_not_convertable_shaders`
- Handling of UDIM textures for texture plugins

### Fixed
- Fixed bug in `DefaultMaterial` that was not taking the good stage

## [3.0.2] - 2023-10-12
### Changed
- Update deps

## [3.0.1] - 2023-10-10
### Changed
- Fix bug in processing DDS when file referenced by USD does not exist.

## [3.0.0] - 2023-09-18
### Changed
- Replaced `EmissiveIntensity` check plugin with `ValueMapping` generic plugin

## [2.5.1] - 2023-10-23
### Fixed
- Remove extraneous pivot transform op created by OV GroupPrims command

## [2.5.0] - 2023-09-22
### Changed
- Change NVTT directory

## [2.4.0] - 2023-09-21
### Added
- USD plugins use `CheckBaseUSD` as a base

### Changed
- Plugins inherit the context from the context plugin

## [2.3.0] - 2023-09-18
### Added
- Added `EmissiveIntensity` check plugin

### Fixed
- Minor fix to `ApplyUnitScale` UI

## [2.2.0] - 2023-09-18
### Changed
- Added `wrap_prim_name` schema argument to `WrapRootPrims` check plugin to set the prim name

## [2.1.0] - 2023-09-01
### Changed
- Use Packman NVTT instead of `omni.flux.resources`

## [2.0.0] - 2023-08-25
### Added
- Added `ResetPivot` check plugin
- Added `WrapRootPrims` check plugin

### Changed
- Changed `ApplyUnitScale` so it uses the prim instead of the prim parent
- Moved `SetDefaultPrimCommand` to `omni.flux.commands`
- Removed requirement for `context_name` in `ResetPivot`
- Simplified command calls for `ResetPivot`

## [1.12.1] - 2023-08-25
### Fixed
- Issue with subidentifier validation for materialshaders plugin

## [1.12.0] - 2023-08-24
### Added
- Support regex patterns for material subidentifier output in schema

## [1.11.0] - 2023-08-17
### Added
- Added Temporary File Cleanup options for `ConvertToDDS` and `ConvertToOctahedral` plugins

### Changed
- Changed `DefaultPrim` to only allow 1 root prim + update the root on the correct stage

## [1.10.0] - 2023-08-07
### Added
- Default material plugin, to add materials when none have been specified on mesh

## [1.9.5] - 2023-08-07
### Added
- Support for new material converter (None -> AperturePBR)

## [1.9.4] - 2023-08-04
### Fixed
- Failure to ingest assets using an older version of AperturePBR

## [1.9.3] - 2023-08-04
### Fixed
- Failure to ingest DDS textures if common naming pattern used.

## [1.9.2] - 2023-08-03
### Fixed
- Bug causing Maya/Max assets to fail import

## [1.9.1] - 2023-07-24
### Changed
- Added support for skinning properties.

## [1.9.0] - 2023-05-23
### Changed
- Use OmniUrl to generate hash
- `ForcePrimvarToVertexInterpolation`: if the mesh is empty, skip it

## [1.8.2] - 2023-05-15
### Fixed
- Fix for 105

## [1.8.1] - 2023-04-27
### Changed
- Change display name for material shaders plugin to be more generic

## [1.8.0] - 2023-04-25
### Added
- Added unit scale check plugin

## [1.7.0] - 2023-04-19
### Added
- Added unit tests for MaterialShaders plugin

## [1.6.0] - 2023-04-17
### Changed
- Changed the arguments passed to the material validation plugin
- Use the material library lib_paths to find shaders
- Added display names to all check plugins

### Fixed
- Fixed crash on relative path ingestion

## [1.5.1] - 2023-04-17
### Fixed
- Fix extension publication

## [1.5.0] - 2023-03-29
### Added
- Plugin to validate shaders in materials

## [1.4.2] - 2023-04-11
### Fixed
- Fixed title and tooltip

## [1.4.1] - 2023-03-28
### Fixed
- Enabled registry to fix tests.

## [1.4.0] - 2023-03-24
### Added
- Adding octahedral and dds validators.

## [1.3.0] - 2023-03-16
### Added
- Be able to control if we want to slow down the print_prim plugin or not.

## [1.2.1] - 2023-03-14
### Fixed
- Fixed crash in add_vertex_indices_to_geom_subset due to invalid input.

## [1.2.0] - 2023-02-28
### Added
- Added plugin to force default prim.

## [1.1.1] - 2023-02-16
### Added
- Added plugins to force references and asset paths to use relative paths.

## [1.1.0] - 2023-02-09
### Changed
- Slowdown the print prims plugins just as a showcase

## [1.0.1] - 2023-02-13
### Added
- Added vertex validation.

## [1.0.0] - 2023-01-26
### Added
- Init commit.
