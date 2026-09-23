# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.3.0]
### Added
- `routes/` package tree — `ingestcraft/` and `stagecraft/{assets,layers,project,textures}/`, each stagecraft area with a co-located `data_models/`. The packages hold no route
- `agentic_enabled` setting (default `false`) gating registration of `ROUTE_SERVICES` with the service factory

### Changed
- `CoreService` skips a configured service the factory does not hold, with an error log, instead of instantiating `None` and failing startup
- Documented the extension's role, settings and routes architecture in `docs/README.md`
- Clarified that the empty route registry adds no endpoints and existing services are independent of its registration setting

## [1.2.3]
### Changed
- Updated extension metadata for Kit SDK 110 compatibility.

## [1.2.2]
### Changed
- Applied new lint rules

## [1.2.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [1.2.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [1.1.3]
## Changed
- Update variables and resource locations for extension testing matrix (ETM) compliance

## [1.1.2]
## Changed
- Update to Kit 106.5

## [1.1.1]
### Fixed
- Fixed tests flakiness

## [1.1.0]
### Changed
- Use generic factory instead of service-specific factory

## [1.0.0] - 2024-03-01
### Added
- Created
