# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.0.4]
### Changed
- Deferred device and memory collection until one update after `USER_READY`, while preserving the App Startup
  transaction's Kit-ready end timestamp and recording the user-ready duration separately.

## [1.0.3]
### Fixed
- The App Startup metric is now marked as executed before any collection work, so a repeated App Ready dispatch
  cannot record it twice.

## [1.0.2]
### Changed
- Updated extension metadata for Kit SDK 110 compatibility.

## [1.0.1]
### Changed
- Modernize python style and enable more ruff checks

## [1.0.0]
### Added
- Init commit
