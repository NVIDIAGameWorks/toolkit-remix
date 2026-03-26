# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0]

### Added
- Per-curve bounds support via `set_curve_bounds()` and `bounds_for()` for independent keyframe clamping
- Elliptical tangent scaling (`_elliptical_scale`) for axis-independent AUTO and SMOOTH tangent computation

### Changed
- AUTO and SMOOTH tangent directions are now projected onto a neighbor-proportioned ellipse instead of a unit circle

## [1.0.0] - 2026-02-11

### Added

- Initial release of FCurveWidget
