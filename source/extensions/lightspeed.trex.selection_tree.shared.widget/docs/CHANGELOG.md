# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.5.3]
## Changed
- Changed `__get_model_from_prototype_path()` to exclude prims that are simultaneously materials
- The Selection Tree will no longer activate solely with mesh prims that are also materials
- Moved `__reference_file_paths()` to generic `prim_utils.py` from `model.py`

## [1.5.2]
## Changed
- Update to Kit 106.5

## [1.5.1]
## Fixed
- Fix a bug where light prototypes cannot be reselected in tree
- Fix naming for item identifiers for test readability

## [1.5.0]
## Changed
- Changed `get_selection` to use USD selection instead of the tree selection for better reliability

## [1.4.4]
## Changed
- update to use omni.kit.test public api

## [1.4.3]
### Fixed
- Fixed flaky test

## [1.4.2]
### Fixed
- Fix unnecessary selection of instance occurring after prim deletion

## [1.4.1]
### Fixed
- Fixed flaky test

## [1.4.0]
### Added
- Use specific icons for light types
- Added more info to tooltips

### Changed
- Made it harder to unintentionally deselect via the selection panel
- Applied Group selection behavior to both group types
- Cleaned up selection expansion logic and add typing
- Made it so clicking top group has no side effect since it can't be selected

### Fixed
- Fixed behavior where panel was not cleared completely on model change
- Fixed bug where add light button was triggered by shift selecting across it
- Only show light prims under "stage lights"

## [1.3.3]
### Fixed
- Fixed case where signals emitted before secondary selection was cleared on model change.

## [1.3.2] - 2024-08-05
### Added
- Added asset not in project directory popup

### Fixed
- Improved flakey tests

## [1.3.1] - 2024-07-16
### Added
- Copy menu hash disabling if there is no hash for the asset

## [1.3.0] - 2024-06-26
### Added
- Added shift-selection support
- Secondary selections for instance items
- Added `get_instance_selection()`

### Changed
- Instance items are no longer included as primary selections
- Removed `get_selection_by_type()`

## [1.2.7] - 2024-07-02
### Changed
- Removed the delete and duplicate button icons for asset reference light items in the selection tree

## [1.2.6]
### Changed
- Added omni.flux.commands as a test dependency

## [1.2.5]
### Changed
- Changed repo link

## [1.2.4]
### Changed
- Cleanup extension + fix default attrs

## [1.2.3] - 2024-06-10
### Added
- Right click menu for selection tree items

## [1.2.2]
### Changed
- Use updated `lightspeed.layer_manager.core` extension

## [1.2.1]
### Changed
- Update to Kit 106

## [1.2.0] - 2024-04-16
### Changed
- Cursor now visibly changes over scroll bars

## [1.1.1]
### Changed
- Set Apache 2 license headers

## [1.1.0] - 2024-03-20
### Added
- Model tree emptied event and subscription method

## [1.0.6] - 2024-03-13
### Changed
- Moved e2e test to its own directory

## [1.0.5] - 2024-02-07
### Added
- Added duplicate button for stage lights in selection tree

## [1.0.4] - 2023-10-20
### Fixed
- Fixed tests

## [1.0.3] - 2023-10-16
### Fixed
- Fixed item not centralized on selection on the scroll frame

## [1.0.2] - 2023-09-18
### Fixed
- Support adding stage lights to meshes
- Remove support for adding references to capture lights

## [1.0.1] - 2022-08-08
### Added
- Geometry subset support to selection tree

## [1.0.0] - 2022-06-09
### Added
- Created
