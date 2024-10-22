# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
