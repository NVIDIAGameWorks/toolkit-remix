# Changelog

## [2.4.2]

### Changed
- Cached channel-selection membership, named framing padding, and simplified editor tests while retaining native insertion and rebuild coverage.

## [2.4.1]

### Changed

- Preserved channel label selection across rebuilds and corrected editor test teardown, numeric-edit notice coverage, and tangent-button selection.

## [2.4.0]

### Changed

- Clear selection on plain blank-canvas clicks, retain selection and controls through constrained group dragging, and add an optional `finalization_context_factory` so storage backends can group changed gestures while preserving Redo for unchanged edits.
- Start the channel tree fully expanded while allowing groups to be collapsed manually.

## [2.3.0]

### Changed

- Added canvas-owned independent axis framing and a single tangent-lock toggle, with tangent-type edits respecting each key's lock state in mixed selections.

### Fixed

- Kept the tangent-lock indicator synchronized when host callbacks change selection during an edit.

## [2.2.0]
### Added

- Added compact Time and Value controls for continuous absolute or shared-offset key editing, sharing selected-key eligibility with toolbar actions and retaining grouped undo and held-drag cancellation.

## [2.1.0]

### Added

- Added shape-preserving curve-click insertion with immediate dragging, one undo action, and logged completion on application focus loss, plus shared selected-key deletion for toolbar and keyboard use, including toolbar-free editors.

## [2.0.0]
### Changed

- Replaced visibility callbacks with channel-selection callbacks and added selection-aware curve operations, grouped undo, and semantic label styling.

## [1.2.2]
### Changed
- Updated curve expansion controls to reflect existing child rows.

## [1.2.1]
### Changed
- Updated extension metadata for Kit SDK 110 compatibility.

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
