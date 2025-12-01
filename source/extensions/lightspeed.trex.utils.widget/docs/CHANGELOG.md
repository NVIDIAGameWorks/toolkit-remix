# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.6.1]
### Changed
- Code formatting improvements

## [1.6.0]
### Added
- Added new common_dialog module, which hosts a new restore_confirmation_dialog method to centralize the reusable messagebox

## [1.5.0]
### Added
- Added quicklayout_wrapper with load_layout function to ensure windows are ready before docking
- Added WorkspaceWidget interface for standardized widget lifecycle management
- Added skip_when_widget_is_invisible decorator for performance optimization
- Added ui.ToolBar support in WorkspaceWindowBase
- Added comprehensive unit tests for decorator functionality

### Changed
- Enhanced WorkspaceWindowBase to call _update_ui in show_window_fn for proper initialization
- Improved tab bar enforcement on window resize and dock changes

### Fixed
- Fixed workspace layout loading race condition causing windows to spawn undocked on first load
- Fixed tab bars reappearing on window resize by enforcing settings after ImGui inheritance

## [1.4.1]
### Added
- Added ability to set initial window size

## [1.4.0]
### Added
- Added create_window method to WorkspaceWindowBase class to support custom windows

## [1.3.0]
### Added
- Added WorkspaceWindowBase class for workspace window integration

## [1.2.2]
## Changed
- Renaming "Remix Categories" to "Render Categories" to better reflect the purpose for newcomers

## [1.2.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [1.2.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [1.1.0]
### Added
- Moved the categories dialog

## [1.0.3]
### Changed
- Changed repo link

## [1.0.2]
### Changed
- Update to Kit 106

## [1.0.1]
### Changed
- Set Apache 2 license headers

## [1.0.0] - 2022-06-09
### Added
- Created
