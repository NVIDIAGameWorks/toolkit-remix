# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.0.3]
### Fixed
- The Session Duration metric is now one-shot, so a repeated shutdown dispatch cannot record it twice.
- Removed the premature Sentry client close from the shutdown callback so flush/close stays owned by
  `TelemetryCore.destroy()`.
- Event registration is now owned solely by the extension.

## [1.0.2]
### Changed
- Updated extension metadata for Kit SDK 110 compatibility.

## [1.0.1]
### Changed
- Modernize python style and enable more ruff checks

## [1.0.0]
### Added
- Init commit
