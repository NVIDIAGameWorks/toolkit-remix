# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.0.3]
### Added
- Added capability-gated **DLSS 3D-Guided Neural Generation [Experimental]** controls to Edit > Preferences > HdRemix Renderer, including Model A/B/C selection, marketing-aligned intensity defaults, Auto Mask, and collapsed advanced controls for highlight recovery and volumetric improvement.

### Fixed
- Reset pre-release DLSS Neural Rendering capture values and persistent setting keys to the release defaults.

## [1.0.2]
### Changed
- Updated extension metadata for Kit SDK 110 compatibility.

## [1.0.1]
### Fixed
- REMIX-5483: Gated the Integrate Indirect Illumination Mode dropdown's runtime push on the Override Capture Value checkbox so loaded capture presets are no longer overwritten when the box is unchecked.
- Enabling Override Capture Value mid-session now pushes the stored Integrate Indirect Illumination Mode to the renderer immediately instead of waiting for the next dropdown change or a restart.

## [1.0.0]
### Added
- REMIX-5483: Add an Edit > Preferences > HdRemix Renderer page with a live "Integrate Indirect Illumination Mode" combo (Importance Sampled / ReSTIR GI / RTX Neural Radiance Cache) matching the dxvk-remix runtime overlay, an "Override Capture Value" checkbox (off by default so captures win on stage open; on to force the global value), driving `rtx.integrateIndirectMode`, forcing `rtx.graphicsPreset=Custom` on user toggles, and stubbing Kit's built-in "Viewport" page with a redirect notice.
