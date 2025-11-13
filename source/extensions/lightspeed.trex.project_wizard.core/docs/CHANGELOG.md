# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.0.3]
### Fixed
- Fixed symlink validation for non-symlink directories by using `get_path_or_symlink()` utility function.

## [2.0.2]
## Fixed
- Fixed broken symlinks detection and updated tests

## [2.0.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [2.0.0]
## Changed
- Updated Pydantic to V2

## [1.4.1]
## Changed
- Update to Kit 106.5

## [1.4.0]
### Changed
- Return setup values in async functions
- Use `omni.kit.window.file.open_stage` instead of `context.open_stage` to open stage for better UI

### Fixed
- Fixed bug with partially initialized projects symlinks

## [1.3.0]
### Changed
- Removed whitespace restrictions

## [1.2.19]
### Fixed
- Fixed tests flakiness

## [1.2.18]
### Changed
- Adding layer validation for existing project file

## [1.2.17]
### Changed
- Update deps

## [1.2.16]
### Changed
- Update dependency

## [1.2.15]
### Changed
- Update deps

## [1.2.14]
### Changed
- Update deps

## [1.2.13]
### Changed
- Update dependency

## [1.2.12]
### Changed
- Changed repo link

## [1.2.11]
### Changed
- Update Kit SDK

## [1.2.10]
### Changed
- Update dependency

## [1.2.9]
### Changed
- Update dependency

## [1.2.8]
### Changed
- Update dependency

## [1.2.7]
### Changed
- Update dependency

## [1.2.6]
- Use updated `lightspeed.layer_manager.core` extension

## [1.2.5]
### Changed
- Update dependency

## [1.2.4]
### Changed
- Update to Kit 106

## [1.2.3]
### Changed
- Update dependency

## [1.2.2]
### Changed
- Update dependency

## [1.2.1]
### Changed
- Set Apache 2 license headers

## [1.2.0] - 2024-02-26
### Added
- Create symlink by default (instead of junction) for Windows

## [1.1.7] - 2024-01-29
### Changed
- Adding filename check for Windows reserved words

## [1.1.6] - 2024-01-24
### Fixed
- Destroy the context at the end of the process to not trigger random listeners

## [1.1.5] - 2024-01-20
### Fixed
- Fixed issue when opening a mod and the `mods` directory doesn't exist in rtx-remix

## [1.1.4] - 2023-10-16
### Changed
- Adding filename check for invalid characters

## [1.1.3] - 2023-12-07
### Fixed
- Create mods dir if doesnt exist

## [1.1.2] - 2023-10-16
### Changed
- Update deps

## [1.1.1] - 2023-09-06
### Fixed
- Fixed creating a project with no capture selected

## [1.1.0] - 2023-09-05
### Changed
- Added extra checks to `is_project_file_valid`
- Added more lenient rule for `_create_symlinks` existing project symlink in `rtx-remix` dir

## [1.0.0] - 2022-06-09
### Added
- Created
