# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.3.0]
### Added
- Particle curve edit groups configuration for size, velocity, and rotation speed animations
- Module-level curve lookup table for mapping primvar attributes to edit groups

### Changed
- Particle property panel now routes animatable curve attributes through edit-group-aware field builders

## [1.2.5]
### Changed
- Applied new lint rules

## [1.2.4]
### Changed
- Modernize python style and enable more ruff checks

## [1.2.3]
### Changed
- Updated to use `TreeItemBase.parent` setter for adding children (compatibility with omni.flux.utils.widget 1.24.0)

## [1.2.2]
### Changed
- Switched to ruff for linting and formatting

## [1.2.1]
### Fixed
- Fixed ItemGroup expansion state not being preserved across refreshes

## [1.2.0]
### Changed
- Renamed the extension to lightspeed.trex.properties_pane.particle.widget

## [1.1.2]
### Fixed
- Added proper task cancellation in destroy method

## [1.1.1]
### Fixed
- Fixed logic to enable particle system creation on prims

## [1.1.0]
### Added
- Added the ability to create particle systems on valid target prims

## [1.0.0]
### Added
- Created
