# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.0.0] - 2025-10-14
### Added
- Init commit.

### Fixed
- Ignored non-init dataclass fields during job queue serialization.
- Closed job stdout handles if stderr log setup fails and tightened callable job parameter typing.
- Made executor finalization nonblocking and improved job wait timeout diagnostics.
- Clarified job result timeout documentation.
- Added standard logging fallbacks for scheduler status messages.
- Tightened in-memory SQLite path detection for the default process executor.
- Added cleanup for job queue event subscriber threads.
