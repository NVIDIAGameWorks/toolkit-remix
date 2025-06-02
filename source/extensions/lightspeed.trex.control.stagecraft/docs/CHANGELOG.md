# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.5.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [1.5.0]
## Added
- Added missing automodule directives for documentation

## [1.4.3]
## Changed
- Update variables and resource locations for extension testing matrix (ETM) compliance

## [1.4.2]
## Changed
- Added a Stage Manager refresh test

## [1.4.1]
## Changed
- Update to Kit 106.5

## [1.4.0]
## Changed
- Unload Stage now closes the stage instead of creating a new project
- Show the home page after unloading the stage

## [1.3.0]
## Changed
- Added support for multiple wizards (open & create)

## [1.2.5]
## Fixed
- Fixed `should_interrupt_shutdown` crash when no context is available

## [1.2.4]
## Changed
- update to use omni.kit.test public api

## [1.2.3]
### Fixed
- Fixed tests flakiness

## [1.2.2]
### Fixed
- Refactored shutdown event

## [1.2.1]
### Fixed
- Fixed tests

## [1.2.0] - 2024-08-13
### Added
- Added `_previous_root_layer_identifier` and `_on_reload_last_workfile()` for reloading previous stages
- Added `__on_open_menu()` for toggling menu UI grabbed from `lightspeed.trex.menu.workfile`

### Changed
- Configured the existing save prompt to open if the user tries to unload a stage with unsaved changes

## [1.1.5]
### Fixed
- Removed test dependency on lightspeed.event.shutdown_base

## [1.1.4]
### Changed
- Changed repo link

## [1.1.3]
### Changed
- Centralized logic to `lightspeed.layer_manager.core` extension

## [1.1.2]
### Changed
- Use updated `lightspeed.layer_manager.core` extension

## [1.1.1]
### Changed
- Update to Kit 106

## [1.1.0] - 2024-04-12
### Changed
- Now reference global wizard window instance and calls `.show_project_wizard()`

## [1.0.3]
### Changed
- Set Apache 2 license headers

## [1.0.2] - 2024-02-28
### Added
- Added an action and event for creating an empty stage

## [1.0.1] - 2024-03-19
## Added
- Add a save prompt that shows up if the project has been modified when closing the app to prevent lost work

## Changed
- Improved UX for going from an open project to saved one by consolidating 2 dialogs into 1 with Save, Save As, Don't Save, Cancel options.

## [1.0.0] - 2024-02-28
### Added
- Created

