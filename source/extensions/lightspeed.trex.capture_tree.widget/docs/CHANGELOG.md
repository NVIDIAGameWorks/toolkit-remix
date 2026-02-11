# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.1.3]
### Changed
- Modernize python style and enable more ruff checks

## [1.1.2]
### Changed
- Switched to ruff for linting and formatting

## [1.1.1]
### Changed
- Refactored to use model's semantic events instead of direct stage/layer subscriptions
- Subscriptions now created in __init__ and controlled by model.enable_listeners()

## [1.1.0]
### Added
- Added WorkspaceWidget interface implementation
- Added skip_when_widget_is_invisible decorator for performance optimization
- Added unit tests for visibility filtering

## [1.0.1]
### Changed
- Updated imports from lightspeed.error_popup.window to omni.flux.utils.dialog

## [1.0.0]
### Added
- Created
