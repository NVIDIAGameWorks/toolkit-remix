# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.3.0]
## Added
- Added a `cleanup` pattern to the stage manager context and listener plugins

## Fixed
- Fixed stage manager not refreshing to USD Notices

## [2.2.0]
## Fixed
- fix false positive error that context isn't set up yet

## [2.1.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [2.1.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [2.0.0]
## Changed
- Updated Pydantic to V2

## [1.7.1]
### Fixed
- Fixed tests flakiness

## [1.7.0]
### Changed
- Make set_context_name() an explicit method for plugins

## [1.6.0]
### Changed
- Build a flat list of data instead of a tree to match the updated StageManagerItem data structure

## [1.5.0]
### Changed
- `get_items` function now returns `StageManagerItem` objects instead of arbitrary data
- Current Stage plugin now returns the full USD tree instead of only the root prims

## [1.4.0]
### Changed
- Create a new stage when no stage exists in a context instead of crashing

## [1.3.0]
### Added
- Added listeners to the USD context base

## [1.2.0]
### Changed
- Override updated `get_items` function instead of `setup`
- Use inheritance for context plugins

## [1.1.1]
### Added
- Added `context_name` field to the USD base

### Fixed
- Fixed dependencies

## [1.1.0]
### Added
- Added `UsdFileContextPlugin` plugin

### Changed
- Implemented `CurrentStageContextPlugin` plugin

## [1.0.0]
### Added
- Created
