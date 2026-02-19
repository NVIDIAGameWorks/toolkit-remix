# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.3.5]
### Added
- OGN node attributes in the properties panel now receive soft/hard bounds and UI step from OGN metadata via `get_ogn_ui_metadata()`, so Remix node attributes display with correct slider ranges and step size
- Added `utils.py` with `UiMetaKeys` enum and `get_ogn_ui_metadata()` (migrated from `lightspeed.trex.logic.core`)
- Added unit tests for `get_ogn_ui_metadata()` in `tests/unit/test_utils.py`

### Changed
- Logic property widget passes OGN metadata as a `ui_metadata` dict into `USDAttributeItem` for bounded attributes
- `get_ogn_ui_metadata` is now imported from local `utils` module instead of `lightspeed.trex.logic.core`

## [1.3.4]
### Changed
- Modernize python style and enable more ruff checks

## [1.3.3]
### Changed
- Updated to use `TreeItemBase.parent` setter for adding children (compatibility with omni.flux.utils.widget 1.24.0)

## [1.3.2]
### Changed
- Switched to ruff for linting and formatting

## [1.3.1]
### Fixed
- Fixed target picker path filtering to include mesh_HASH and light_HASH prims, not just their children

## [1.3.0]
### Added
- Added better support for flexible OGN types (union/any) with read-only display and guidance text

### Changed
- Improved OGN attribute default value handling with proper USD type conversion
- Disabled override deletion for OGN node attributes to prevent type removal

### Fixed
- Fixed panel rebuild targeting correct dynamic content frame

## [1.2.5]
### Changed
- Replaced text buttons with icon buttons for edit and delete actions
- Improved existing graphs list layout with dedicated section header

## [1.2.4]
### Changed
- Configured ConstAssetPath field to use relative paths

## [1.2.3]
### Fixed
- Restored Delete button for logic graphs in properties panel

## [1.2.2]
### Changed
- Improved node type description display in properties panel

## [1.2.1]
### Added
- Added StagePrimPicker integration for OmniGraph target relationship inputs

### Fixed
- Fixed ItemGroup expansion state not being preserved across refreshes

## [1.2.0]
### Added
- Added Delete button for logic graphs in properties panel

## [1.1.0]
### Added
- Added create and edit logic graph buttons to properties panel
- Added display of existing logic graphs with edit capability

### Changed
- Integrated with LogicGraphCore for graph creation and editing

## [1.0.1]
### Changed
- Code formatting improvements

## [1.0.0]
### Added
- Created
