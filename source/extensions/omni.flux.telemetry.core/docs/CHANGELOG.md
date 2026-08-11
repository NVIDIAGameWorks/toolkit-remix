# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.1.5]
### Fixed
- Retained the telemetry core handle through extension shutdown so stale callbacks can safely reach the
  process-global Sentry SDK; a later startup still replaces it with a fresh core.

## [1.1.4]
### Changed
- Updated extension metadata for Kit SDK 110 compatibility.

## [1.1.3]
### Changed
- Applied new lint rules

## [1.1.2]
### Changed
- Switched to ruff for linting and formatting

## [1.1.1]
### Fixed
- Fixed usage of the updated `omni.flux.utils.common.git` module

## [1.1.0]
### Changed
- Use more accurate value for the app distribution

## [1.0.1]
### Fixed
- Fixed machine ID generation to be unique and deterministic.

## [1.0.0]
### Added
- Init commit.
