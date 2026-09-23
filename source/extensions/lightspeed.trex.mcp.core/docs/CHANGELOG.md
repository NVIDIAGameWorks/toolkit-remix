# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.3.0]
### Changed
- Changed the preferred port from `8000` to `18014`, with fallback limited to `18014–18019`. Update clients from `http://127.0.0.1:8000/mcp/` to `http://127.0.0.1:18014/mcp/`
- MCP clients now see a smaller, more relevant tool list. The transport's own health, readiness, status and asyncapi endpoints, the OpenAPI metadata routes and the root-level UI-automation routes are dropped from the tool manifest; every other route is still exposed as a tool
- Log the complete connection URL at warning level whenever port fallback selects a different endpoint
- Document the current transports and bundled protocol support without planned upgrade or removal claims
- Remove duplicated input-parameter prose from MCP tool descriptions while preserving authored guidance, response documentation and input schemas
- Allow one second for graceful shutdown so an idle server can close without a spurious timeout error

### Added
- Publish a current-user-only Windows discovery manifest after successful MCP startup, including fallback endpoints, and remove it on clean shutdown without deleting a newer instance's record

### Removed
- MCP workflow prompts; the server exposes Toolkit operations as tools

### Fixed
- Reserve MCP listener addresses exclusively on Windows so another Toolkit instance selects a fallback port.
- Publish loopback connection URLs for wildcard MCP and REST bind addresses.

## [1.2.7]
### Added
- Added a `transport` setting to select the MCP transport, with the legacy `sse` transport still available.

### Changed
- Switched the default MCP transport to Streamable HTTP, moving the endpoint from `/sse` to `/mcp`.

## [1.2.6]
### Added
- Added a `SERVICE_READY service=mcp` milestone after the MCP endpoint begins accepting connections.

### Changed
- Defer MCP server startup until Kit reports app ready
- Replaced the misleading post-shutdown initialization log with the bind-complete readiness milestone.
- Gracefully close active MCP connections during extension shutdown.

## [1.2.5]
### Fixed
- Corrected stale tool names and argument names in the `replace_model_asset` prompt.

## [1.2.4]
### Fixed
- Prevented MCP server port bind failures from aborting Toolkit launch.

## [1.2.3]
### Changed
- Updated extension metadata for Kit SDK 110 compatibility.

## [1.2.2]
### Changed
- Modernize python style and enable more ruff checks

## [1.2.1]
### Changed
- Use Flux Pip Archive instead of LSS Pip Archive

## [1.2.0]
### Changed
- Optimized the MCP server initialization by running it in a separate thread

## [1.1.0]
### Added
- Added settings to modify the MCP server's host, port, and log level

### Fixed
- Fixed the MCP server to use a different port when the default port is already in use

## [1.0.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [1.0.0]
### Added
- Created
