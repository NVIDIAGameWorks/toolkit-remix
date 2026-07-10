# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.7.0]
### Changed
- Particle curve editor outlets now use the shared USD logical group outlet item.

### Fixed
- Seeded legacy animated particle attributes for every selected target before opening curve editors.
- Routed legacy animated particle seeding through the shared grouped primvar command.
- Particle curve edit-group rows now carry the ordered selected particle target paths used by the shared USD property builders.
- Particle curve edit-group schema validation now fails on missing required curve attrs instead of falling back to scalar definitions.

## [1.6.1]
### Added
- Added layer-transfer callback forwarding for particle property menus.

## [1.6.0]
### Added
- Added silent legacy particle upgrades that seed the currently opened animated size, color, or rotation control from legacy values

### Changed
- Particle curve editor buttons now use runtime schema display-group metadata for property panel placement
- Rendered the particle `General` group first so schema-grouped primary controls appear at the top

### Fixed
- Hid particle curve editor infinity companion attributes from regular property rows when a combined curve editor outlet owns them

## [1.5.0]
### Fixed
- Resolved particle prim paths so multi-selection counts unique prototype-backed particle targets without duplicating equivalent paths

## [1.4.0]
### Changed
- Particle bounds metadata now flows through `ParticleBoundsAdapter` using canonical `limits` parsing with legacy range fallback, aligning particle clamping behavior with the shared bounds refactor

## [1.3.1]
### Fixed
- Particle attribute fields now read `customData.limits` from the USD schema and pass min/max bounds to the property widget, preventing crashes when out-of-range values are typed into numeric fields

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
