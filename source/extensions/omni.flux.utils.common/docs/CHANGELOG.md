# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.18.0]
### Added
- Added the ability to write lists to metadata

## [2.17.0] - 2024-06-04
### Added
- Added `get_invalid_extensions()`

## [2.16.1]
### Changed
- Fixed docstring

## [2.16.0] - 2024-03-14
### Changed
- Made `omni.kit.window.file` an optional dependency and added fallback method

## [2.15.1]
### Changed
- Set Apache 2 license headers

## [2.15.0] - 2024-02-27
### Added
- Add `uac` and `symlink` utils

## [2.14.1] - 2024-02-09
### Added
- Add `limit_recursion` decorator used to limit recursive calls
- Add unit tests for `limit_recursion`
- Add `Serializer` object which acts as an interface and registry for custom serialization/deserialization routines
- Add unit tests for `Serializer`

## [2.14.0] - 2024-01-12
### Added
- `get_omni_prims()`: List of internal Omniverse Kit prims

## [2.13.0] - 2023-12-15
### Added
- `open_file_using_os_default()`: Open files in OS native programs

## [2.12.0] - 2023-12-06
### Changed
- Return the result of OmniUrl delete
- `write_file()`: check that we can write in the directory

## [2.11.0] - 2023-11-15
### Added
- Hash to OmniUrl

## [2.10.0] - 2023-10-31
### Added
- Add `decorators` utils
- Add `copy` feature for event

## [2.9.0] - 2023-10-23
### Added
- Add `get_udim_sequence()`, `is_udim_texture()`, `texture_to_udim()`

## [2.8.1] - 2023-10-10
### Added
- Extend OmniURL interface to support querying if path is a file or directory

## [2.8.0] - 2023-10-03
### Changed
- Raise `IOError` when there is a read error

## [2.7.0] - 2023-08-17
### Added
- Added `cleanup_file()`
- Added ability for `OmniUrl` to be used as a Pydantic Type

## [2.6.1] - 2023-08-04
### Fixed
- `--no-window` on the test

## [2.6.0] - 2023-06-09
### Added
- Added `get_new_hash()` and `deferred_destroy_tasks()`

## [2.5.2] - 2023-04-04
### Fixed
- Fix linux omniUrl tests

## [2.5.1] - 2023-03-29
### Fixed
- Fixe test dependency for ETM

## [2.5.0] - 2023-03-29
### Added
- Added OmniUrl to provide a pathlib like wrapper around Omni client urls

## [2.4.0] - 2023-03-27
### Added
- Added functions for hashing files and storing metadata adjacent to files.

## [2.3.0] - 2023-02-24
### Added
- improved cross platform compatibility of "is_absolute_path" in `path_utils`
- added unit test for "is_absolute_path"

## [2.2.0] - 2023-02-22
### Changed
- Changed test structure to match unit/e2e format

## [2.1.0] - 2023-02-08
### Added
- Add "read_file", "read_json_file", "write_file", "write_json_file" in `path_utils`

## [2.0.0] - 2023-01-17
### Added
- Add layer utils
- Add `__all__` attributes to all modules which might break some imports

## [1.2.0] - 2022-09-26
### Added
- Add path utils

## [1.1.1] - 2022-07-08
### Fixed
- Fix doc to generate docstring from `__init__`

## [1.1.0] - 2022-07-01
### Changed
- Centralize event and event subscription in utils common + format/lint

## [1.0.1] - 2022-06-15
### Changed
- Fixed icon path in build file

## [1.0.0] - 2022-06-13
### Added
- Init commit. Moved async_wrap from widget utils, created reset_default_attrs
