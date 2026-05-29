# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.0.0]
### Added
- REMIX-5483: Add an Edit > Preferences > HdRemix Renderer page with a live "Integrate Indirect Illumination Mode" combo (Importance Sampled / ReSTIR GI / RTX Neural Radiance Cache) matching the dxvk-remix runtime overlay, an "Override Capture Value" checkbox (off by default so captures win on stage open; on to force the global value), driving `rtx.integrateIndirectMode`, forcing `rtx.graphicsPreset=Custom` on user toggles, and stubbing Kit's built-in "Viewport" page with a redirect notice.
