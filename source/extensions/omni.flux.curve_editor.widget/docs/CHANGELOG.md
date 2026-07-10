# Changelog

## [1.2.0]
### Changed
- Removed USD primvar storage from the generic curve editor runtime; USD-backed property editing now lives in `omni.flux.property_widget_builder.model.usd`.
- Curve editor widgets now consume `GroupedKeysModel` payload storage and convert `FCurve` data locally for rendering.
- Moved curve payload conversion helpers out of the removed `model` package.
- Primvar curve commands and models now accept ordered prim path lists so multi-target edits preserve per-target undo payloads

### Fixed
- Curve primvar commands now skip deleted target prims while snapshotting, writing, and restoring remaining targets

### Removed
- Removed the old `CurveModel` and `InMemoryCurveModel` storage contracts.
- Removed the no-op curve editor extension startup entrypoint.

## [1.1.0]
### Added
- Hierarchical curve tree panel with per-curve visibility, add/delete controls, and colored labels
- Per-curve bounds support for independent keyframe clamping per attribute
- Auto fit-to-data when creating new curves
- Toolbar separator and background styling improvements

### Changed
- Canvas now passes per-curve bounds through to FCurveWidget
- Curve editor window is no longer collapsible

## [1.0.0] - 2026-02-11

### Added
- Initial release, forked from `omni.anim.curve_editor`
