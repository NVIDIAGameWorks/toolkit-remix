# lightspeed.trex.service.core

The single entry point for the Toolkit's REST surface. It defines the Toolkit's REST routes under `routes/`, registers
the top-level route services with `omni.flux.service.factory`, and mounts each configured service's router on the
`omni.services.core` app. `lightspeed.trex.mcp.core` adapts whatever this extension publishes into MCP tools; it
defines no route of its own.

## Responsibilities

- Define the Toolkit's REST routes, one `ServiceBase` per area under `routes/`.
- Register `ROUTE_SERVICES` with the service factory at startup.
- Instantiate each service named in `exts/lightspeed.trex.service.core/services` from the factory and register its
  router, tags and OpenAPI description.
- Initialize FastAPI endpoint versioning against the configured vendor media type, once per app.
- When the extension shuts down, deregister the mounted routers, remove their OpenAPI tags and unregister the route
  services. Disabling then stops serving the REST API, and re-enabling or hot-reloading mounts each route exactly once.

## Non-Responsibilities

- **USD operations.** Routes delegate stage reads and writes to their backing core extensions, which also own the
  request and response models: [lightspeed.layer_manager.core](../../lightspeed.layer_manager.core/docs/README.md)
  for projects and layers, `lightspeed.trex.asset_replacements.core.shared` for assets and
  [lightspeed.trex.texture_replacements.core.shared](../../lightspeed.trex.texture_replacements.core.shared/docs/README.md)
  for textures.
- **Anything MCP.** `lightspeed.trex.mcp.core` owns the `FastMCP` instance, the transport, and which
  routes become tools. This extension never imports it.
- **Flux services.** `MassValidatorService` registers itself from `omni.flux.validator.mass.service`; the ingestcraft
  routes mount it from the factory.

## Architecture

**`TrexCoreServiceExtension`** (`extension.py`) — owns the startup and shutdown lifecycle. It registers the route
services before constructing `CoreService`, so the configured names resolve, and unregisters them after destroying it.

**`CoreService`** (`service.py`) — reads the `services` setting, pulls each named service from the
service factory, and calls `main.register_router` for each one. `_instantiate_services` logs an
error and skips any configured name the factory does not know. Endpoint versioning (its middleware, OpenAPI
generator and vendor media type) outlives the extension, because Starlette refuses new middleware once the app has
served a request, so a later `CoreService` reuses what the first one installed. `destroy` deregisters the mounted
routers and removes the OpenAPI tags it added.

**`routes/`** — the route services, one package per area:

| Package | Service | Serves |
|---|---|---|
| `stagecraft/` | `StageCraftService` | `/stagecraft`, including the routers of the four areas below |
| `stagecraft/project/` | `ProjectManagerService` | `/stagecraft/project` — open, close and read the loaded project |
| `stagecraft/layers/` | `LayerManagerService` | `/stagecraft/layers` — the layer stack and edit target |
| `stagecraft/assets/` | `AssetReplacementsService` | `/stagecraft/assets` — prim paths, asset references, default asset directories, selection |
| `stagecraft/textures/` | `TextureReplacementsService` | `/stagecraft/textures` — texture discovery and overrides |
| `ingestcraft/` | `IngestCraftService` | `/ingestcraft`, mounting `MassValidatorService` with the ingestion schemas |

Each stagecraft area also has a `data_models/` package for models a route owns. The areas above take their models from
their core extensions, so those packages are empty.

### Route behavior

- Layer tree, type-filtered and immediate-sublayer listings (`remix_get_layers`, `remix_get_sublayers`) read the
  service's configured USD context and report each layer's explicit `muted` state. After `remix_mute_layer`, query
  either one and check the target layer's `muted` boolean to verify the mute or unmute.
- Layer-membership validation rejects a request with a 422 error when the configured USD context has no open stage,
  before invoking the core operation. Open a project in that context before querying its sublayers.
- Forced texture replacement requests must include `expected_current_textures` with one unique entry for every
  replacement target. The request succeeds only when those values exactly match the current edit-layer opinions; stale
  requests return HTTP 422 without modifying the layer.

## Settings

- `exts/lightspeed.trex.service.core/header`: vendor media type for endpoint versioning,
  default `application/lightspeed.remix.service+json`. Applied once per app, by the first `CoreService` to start, so a
  change takes effect at the next app start, not on a hot reload.
- `exts/lightspeed.trex.service.core/services`: the list of services to mount. Each entry needs
  `name` (the class registered with the service factory), `context`, `title` and `description`.
  An entry naming a class the factory does not hold is skipped, not fatal.
