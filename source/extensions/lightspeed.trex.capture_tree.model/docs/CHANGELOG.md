# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.5.2]
### Changed
- Modernize python style and enable more ruff checks

## [1.5.1]
### Changed
- Switched to ruff for linting and formatting

## [1.5.0]
### Added
- Added semantic event subscriptions: subscribe_stage_opened_or_closed(), subscribe_sublayers_changed()
- Added layer event handling in enable_listeners() for sublayer changes

### Changed
- Model now owns all data-related event subscriptions, widgets subscribe to model events

## [1.4.0]
### Added
- Added progress data caching for improved performance
- Added get_progress_data() method to retrieve cached progress values

### Changed
- Improved async task cancellation using task.cancel() instead of boolean token
- Modernized type hints throughout the module

## [1.3.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [1.3.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [1.2.8]
## Changed
- Updated test to use `deps` instead of `.deps` dir

## [1.2.7]
## Changed
- Update to Kit 106.5

## [1.2.6]
## Changed
- update to use omni.kit.test public api

## [1.2.5]
### Fixed
- Fixed tests flakiness

## [1.2.4]
### Changed
- Update to Kit 106

## [1.2.3]
### Changed
- Set Apache 2 license headers

## [1.2.2] - 2024-03-13
### Changed
- Moved e2e test to its own directory

## [1.2.1] - 2024-02-15
### Fixed
- Header and spacing system

## [1.2.0] - 2024-02-12
### Added
- Added more comprehensive column headers and tooltips to the captures list

## [1.1.1] - 2023-10-16
### Fixed
- Fix on destroy

## [1.1.0] - 2023-10-10
### Changed
- Optimize capture progress fetching

## [1.0.0] - 2023-05-18
### Added
- Created
