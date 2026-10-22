# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [3.0.0]

### Changed

- Select keys on press and retain the full editable selection through constrained group dragging and release; replace `FCurveKeySelected` and `FCurveTangentSelected` fill overrides with gamma-6 curve colors and contrasting native borders, preserving alpha and inherited borders on deselection.

## [2.0.0]

### Changed

- Removed `FCurveWidget.fit_to_data()` in favor of canvas-owned framing and made tangent-type edits respect each selected key's lock state.

### Fixed

- Moved no-side tangent-edit regression coverage into the UI-isolated unit suite.

## [1.4.0]
### Added

- Added validated shared-offset editing with stable key identities and stationary times, persistence before change events, shared editable selection, and a bounded fallback for coarse curve-click position estimates.

## [1.3.0]

### Added

- Added native curve-segment clicks that insert shape-preserving keys and reuse key dragging, with logs for rejected insertions and key, tangent, and insertion gestures finalized before manager replacement or destruction.

## [1.2.0]
### Changed

- Added curve evaluation, corrected insertion notifications and selection highlighting after rebuilds, and limited selected-key deletion and tangent edits to visible curves.

## [1.1.1]
### Changed
- Updated extension metadata for Kit SDK 110 compatibility.

## [1.1.0]

### Added
- Per-curve bounds support via `set_curve_bounds()` and `bounds_for()` for independent keyframe clamping
- Elliptical tangent scaling (`_elliptical_scale`) for axis-independent AUTO and SMOOTH tangent computation

### Changed
- AUTO and SMOOTH tangent directions are now projected onto a neighbor-proportioned ellipse instead of a unit circle

## [1.0.0] - 2026-02-11

### Added

- Initial release of FCurveWidget
