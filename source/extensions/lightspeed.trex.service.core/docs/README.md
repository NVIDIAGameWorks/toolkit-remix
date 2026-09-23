# lightspeed.trex.service.core

The single entry point for the Toolkit's REST surface. It reads the configured service list,
and mounts each service's router on the `omni.services.core` app. `lightspeed.trex.mcp.core`
adapts whatever this extension publishes into MCP tools; it defines no route of its own.

## Responsibilities

- Instantiate each service named in `exts/lightspeed.trex.service.core/services` from
  `omni.flux.service.factory` and register its router, tags and OpenAPI description.
- Initialize FastAPI endpoint versioning against the configured vendor media type.
- Deregister the mounted routers when the extension shuts down.

## Non-Responsibilities

- **USD operations.** Services delegate stage reads and writes to their backing core extensions.
- **Anything MCP.** `lightspeed.trex.mcp.core` owns the `FastMCP` instance, the transport, and which
  routes become tools. This extension never imports it.
- **Service implementations.** Service extensions register their classes with the factory;
  the configured service list selects which ones this extension mounts.

## Architecture

**`TrexCoreServiceExtension`** (`extension.py`) — owns the startup and shutdown lifecycle,
including construction and cleanup of `CoreService`.

**`CoreService`** (`service.py`) — reads the `services` setting, pulls each named service from the
service factory, and calls `main.register_router` for each one. `_instantiate_services` logs an
error and skips any configured name the factory does not know. `destroy` deregisters the
mounted routers.

## Settings

- `exts/lightspeed.trex.service.core/header`: vendor media type for endpoint versioning,
  default `application/lightspeed.remix.service+json`.
- `exts/lightspeed.trex.service.core/services`: the list of services to mount. Each entry needs
  `name` (the class registered with the service factory), `context`, `title` and `description`.
  An entry naming a class the factory does not hold is skipped, not fatal.
- `exts/lightspeed.trex.service.core/agentic_enabled`: register `ROUTE_SERVICES` with the service
  factory at startup, default `false`. `ROUTE_SERVICES` is empty, so enabling this setting
  currently adds no endpoints. It does not gate the configured service list.
