# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.4.0]
### Changed
- Implemented methods required to activate/deactivate interaction plugins

## [1.3.0]
### Added
- Added listener subscriptions to the USD Base
- Added selection synchronization to the USD Base

## [1.2.0]
### Added
- Add recursive traversal option in the `StageManagerUSDInteractionPlugin` base
- Add ability to get the context name from the context and propagate it down to every child plugin
- Added `AllLightsInteractionPlugin` plugin

### Changed
- Moved compatibility check from `AllPrimsInteractionPlugin` to base interaction class

## [1.1.1]
### Added
- Added `context_name` field to the USD base

### Changed
- Propagate the `context_name` field for all children plugins

### Fixed
- Fixed dependencies

## [1.1.0]
### Changed
- Added more compatible plugins for `AllPrimsInteractionPlugin`
- Check `context_filters` compatibility for `AllPrimsInteractionPlugin`

## [1.0.0]
### Added
- Created
