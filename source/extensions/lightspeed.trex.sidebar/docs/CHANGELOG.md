# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.2.2]
### Changed
- Modernize python style and enable more ruff checks

## [1.2.1]
### Changed
- Updated WorkspaceWidget interface to call super().show() for proper visibility tracking

## [1.2.0]
### Added
- Added disabled_tooltip support for sidebar items

### Changed
- Reimplemented sidebar using ui.ToolBar for improved docking behavior
- Simplified size management by leveraging ToolBar's built-in fixed-size handling

### Fixed
- Fixed hot-reload errors caused by asyncio event loop initialization
- Fixed workspace layout loading race condition on first load

## [1.1.1]
### Fixed
- Fixed Test assets to large to work without LFS

## [1.1.0]
### Changed
- Update the documentation for Pydantic V2 compatbility

## [1.0.4]
### Changed
- Changed repo link

## [1.0.3]
### Changed
- Use updated `lightspeed.layer_manager.core` extension

## [1.0.2]
### Changed
- Update to Kit 106

## [1.0.1]
### Changed
- Set Apache 2 license headers

## [1.0.0] - 2024-02-28
### Added
- Created
