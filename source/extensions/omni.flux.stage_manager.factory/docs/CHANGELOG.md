# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.2.0]
### Changed
- Split context plugins setup between `setup()` and `get_items()`
- Add the ability not to display filters
- Changed interactions to not have `context_filters` separate from `filters`
- Centralized compatibility check for interaction plugins
- Filter context items at the interaction-level while allowing tree models to also filter afterwards (for recursive item creation)

## [1.1.1]
### Changed
- Added the ability to set the context from the core to the interaction plugin

### Fixed
- Fixed model serialization

## [1.1.0]
### Changed
- Implemented plugin base classes

## [1.0.0]
### Added
- Created
