# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.6.2]
### Changed
- Modernize python style and enable more ruff checks

## [1.6.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [1.6.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [1.5.3]
### Changed
- Update deps

## [1.5.2]
### Changed
- Set Apache 2 license headers

## [1.5.1] - 2023-10-05
### Fixed
- Fix long file name

## [1.5.0] - 2023-08-02
### Changed
- Optimization: remove text to image

## [1.4.0] - 2023-01-06
### Added
- kwargs to be able to disable the title and burger menu

## [1.3.0] - 2022-08-03
### Added
- Add "get_selection" for the tree

## [1.2.1] - 2022-07-08
### Fixed
- Fix doc to generate docstring from `__init__`

## [1.2.0] - 2022-06-22
### Added
- tree_panel: be able to set the selection by code. Be able to enable or disable an item

## [1.0.2] - 2022-06-22
### Fixed
- Fix issue was that the widget was storing the tree items in a dict by title, preventing duplicate item creation. Now it stores them by id.

### Changed
- Disable double click of title in tree panel widget
- Enable and expose single click of title in tree panel widget

## [1.0.1] - 2022-06-13
### Changed
- destroy() implementations now use reset_default_attrs helper

## [1.0.0] - 2022-04-19
### Added
- Init commit.
