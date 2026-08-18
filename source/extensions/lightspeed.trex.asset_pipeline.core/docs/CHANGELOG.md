# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.1.1]
### Fixed
- Fixed the end-to-end progress test to observe each committed targeted progress notification.

## [1.1.0]
### Added
- Added a reusable typed texture-processing job with asynchronous progress, immutable results, explicit codecs, source-relative semantic output paths, direct USD shader metadata, and transactional local or remote publication.

### Fixed
- Preserved normal-map convention and collected USD dependency identity in stable published texture paths.
- Kept project-independent texture outputs in their durable queue job directory when no publication URL is supplied.

## [1.0.0]
### Added
- Created the Remix asset pipeline foundation with a stable asset item, texture conversion steps, metadata sidecars, canonical step ordering, unit coverage, and high-level README architecture diagrams.
