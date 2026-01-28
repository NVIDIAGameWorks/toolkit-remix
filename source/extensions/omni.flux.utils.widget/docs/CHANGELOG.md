# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.23.1]
### Changed
- Switched to ruff for linting and formatting

## [1.23.0]
### Added
- Added `ScrollingTreeWidget` - a reusable widget that encapsulates `TreeWidget` with `ScrollingFrame` and optional alternating row backgrounds
- Added `iter_visible_items()` method to `ScrollingTreeWidget` using iterative BFS to yield items in correct visual display order
- Added `scroll_to_items()` async method to `ScrollingTreeWidget` for scrolling to specific items with proper frame synchronization
- Added `get_children_count()` method to `TreeModelBase` for efficient item counting without creating intermediate lists

## [1.22.0]
### Added
- Added 'visible_descendant_count' to TreeWidget

## [1.21.1]
### Fixed
- Fixed resource functions to handle uninitialized Carb gracefully during docs build

## [1.21.0]
### Added
- Added get_quicklayout_config() function for accessing QuickLayout JSON files
- Added get_menubar_ignore_file() function for accessing menubar filter configuration

## [1.20.3]
### Changed
- Use Flux Pip Archive instead of Kit Pip Archive

## [1.20.2]
### Changed
- Modernize typing and minor cleanup

## [1.20.1]
### Fixed
- Fixed Test assets to large to work without LFS

## [1.20.0]
### Changed
- Update the documentation for Pydantic V2 compatbility

## [1.19.3]
### Changed
- Update to Kit 106.5

## [1.19.2]
### Fixed
- typing fix

## [1.19.1]
### Fixed
- Fixed crash when item is none in `TreeModelBase`'s `can_item_have_children`

## [1.19.0]
### Added
- Added `AlternateRowWidget` and related widgets to allow easy implementation of alternating row colors in `TreeWidget`

## [1.18.3]
### Fixed
- Fixed tests flakiness

## [1.18.2]
### Added
- Added `iter_visible_children` method to `TreeWidget`

## [1.18.1]
### Fixed
- Fixed an issue in `TreeWidget` where `subscribe_selection_changed` is not triggered if `select_all_children` is False

## [1.18.0]
### Changed
- Added `subscribe_selection_changed` function to the `TreeWidget`

## [1.17.1]
### Changed
- Improved branch building function for `TreeDelegateBase`

## [1.17.0]
### Changed
- Changed the `TreeModelBase` to be generic

## [1.16.1] - 2024-07-19
### Fixed
- Adding a trailing slash to end of dirname when double-clicking on file in dialog

## [1.16.0]
### Added
- Added centralized LayerTree widget

## [1.15.3] - 2024-06-26
### Changed
- `destroy_file_picker()` now handles arguments

## [1.15.2]
### Changed
- Update deps

## [1.15.1] - 2024-04-10
### Fixed
- File browser search bar

## [1.15.0] - 2024-04-04
### Added
- Added a function to add hover actions for widgets

## [1.14.1]
### Changed
- Set Apache 2 license headers

## [1.14.0] - 2024-04-03
### Added
- Added global `file_picker_dialog` variable
- There can now only be one file picker open at a time
- Added `destroy_file_picker()`

## [1.13.0] - 2024-03-22
### Added
- Pinning functionality for `PropertyCollapsableFrame`

## [1.12.0] - 2024-01-19
### Changed
- Open last known directory instead of nothing when `current_file` is unset

## [1.11.2] - 2023-12-04
### Changed
- Update deprecated ImageFont methods

## [1.11.1] - 2023-10-13
### Added
- Add `identifier` for tests

## [1.11.0] - 2023-08-28
### Added
- Use `InfoIconWidget`
- Be able to generate rotated text to image

## [1.10.0] - 2023-08-02
### Changed
- Optimization: remove text to image

## [1.9.0] - 2023-07-24
### Added
- Multi file selection

## [1.8.7] - 2023-05-17
### Fixed
- Fix file picker filter

## [1.8.6] - 2023-05-15
### Fixed
- Fix file picker auto extension

## [1.8.5] - 2023-03-30
### Fixed
- Fix file picker crash

## [1.8.4] - 2023-03-27
### Fixed
- Fix extensions filtering for the file picked.

## [1.8.3] - 2023-03-10
### Fixed
- Fixed info window overrunning the width and height of the window

## [1.8.2] - 2023-02-27
### Fixed
- Auto-add the extension in the file picker

## [1.8.1] - 2023-02-27
### Fixed
- Fixed issue in validation logic for directories

## [1.8.0] - 2023-02-15
### Added
- Added `get_test_data()`

## [1.7.2] - 2023-01-25
### Changed
- Added `file_picker` to the `file_pickers` package init

## [1.7.1] - 2023-01-13
### Changed
- Use null defaults instead of lambdas in `file_picker`

## [1.7.0] - 2022-12-20
### Added
- Added `background_pattern`

## [1.6.1] - 2022-12-19
### Added
- Filepicker: Added ability to pass bookmarks
- Filepicker: Added ability to override apply string
- Filepicker: Added ability to give a validation failure callback

## [1.6.0] - 2022-12-09
### Changed
- Filepicker: set `show_grid_view` to False by default

## [1.5.0] - 2022-11-16
### Added
- Added a loader widget

## [1.4.2] - 2022-11-03
### Fixed
- Fixed file matching bug in File Picker

## [1.4.1] - 2022-10-28
### Fixed
- Re-publish

## [1.4.0] - 2022-09-26
### Changed
- File Picker can now select directories

## [1.3.0] - 2022-09-26
### Added
- Add File Picker

## [1.2.0] - 2022-07-14
### Added
- PropertyCollapsableFrame: function to get the root frame
- PropertyCollapsableFrame: be able to enable or disable the frame

## [1.1.1] - 2022-07-07
### Fixed
- PropertyCollapsableFrame: fix first mouse hovered

## [1.1.0] - 2022-07-01
### Added
- utils: add PropertyCollapsableFrame

## [1.0.2] - 2022-06-16
### Added
- create_label_with_font will stringify given text parameter rather throw

## [1.0.1] - 2022-06-13
### Added
- create_button_from_widget which unifies button click behavior

## [1.0.0] - 2022-04-19
### Added
- Init commit.
