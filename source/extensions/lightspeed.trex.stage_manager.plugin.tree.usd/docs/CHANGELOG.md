# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.1.1]
### Changed
- Modernize python style and enable more ruff checks

## [2.1.0]
### Added
- Added `_build_item()` factory method to `CategoryGroupsModel` and `MeshGroupsModel`

### Changed
- Updated `CategoryGroupsModel` and `MeshGroupsModel` to use model-level item recycling via `_build_item()` for parent group items, preserving tree expansion states across refreshes
- Child items now use `_build_item()` directly (non-recycled) to prevent duplicate item issues
- Replaced `add_child()` calls with direct `parent` property assignment for tree item hierarchy

## [2.0.2]
### Changed
- Switched to ruff for linting and formatting

## [2.0.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [2.0.0]
## Changed
- Updated Pydantic to V2

## [1.3.0]
### Added
- Added alphabetical sorting for the tree items

## [1.2.2]
## Changed
- rename trex prim utility names for clarity

## [1.2.1]
### Changed
- Made mesh grouping always use parent/child hierarchy labeling for children

## [1.2.0]
### Fixed
- Fixed issue where a prim could not be added to more than 1 category

## [1.1.0]
### Added
- Created with stage manager mesh tab

## [1.0.0]
### Added
- Created
