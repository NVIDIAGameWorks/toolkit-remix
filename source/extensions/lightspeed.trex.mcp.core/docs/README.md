# lightspeed.trex.mcp.core

Provides the RTX Remix Toolkit MCP server. It exposes Toolkit REST APIs as tools through a FastMCP HTTP endpoint.

## Responsibilities

- Start the FastMCP server for RTX Remix Toolkit on the configured transport.
- Mount the Toolkit REST API as MCP tools under the `remix` namespace, less the transport's own infrastructure endpoints.
- Bind the configured port and, when range fallback is enabled, retry startup within ports `18014–18019` if the initial server bind fails.
- Publish `SERVICE_READY service=mcp` after Uvicorn is accepting connections on the selected endpoint.
- Close active connections through Uvicorn's supported shutdown lifecycle.

## Non-Responsibilities

- Defining REST API routes. Those are owned by the Toolkit service extensions.
- Owning user-facing MCP UI. This extension provides the server core only.
- Managing external MCP clients after they connect to the server endpoint.

## Architecture

- `MCPCore` reads the extension settings, builds a FastMCP server from the active `omni.services.core` FastAPI app, mounts it into the supplied MCP instance, and starts the configured transport.
- `_CURATED_ROUTE_MAPS` decides which routes become tools; first match wins. It is a deny-list: three
  patterns drop the transport's health/readiness endpoints, the OpenAPI metadata routes and the root-level
  UI-automation routes, and a trailing catch-all keeps everything else as a `TOOL`. A route prefix added by
  a new capability therefore reaches the manifest without editing this extension. The catch-all is required,
  not cosmetic: fastmcp appends its own default mappings after these, and those send a bare `GET` to
  `RESOURCE`, so without it every read operation would drop out of the tool manifest.
- `_ServiceReadyServer` publishes the Windows discovery manifest and timestamped readiness marker after Uvicorn startup, rather than after the long-running server exits.
- `discovery` atomically publishes the manifest with current-user-only file permissions and removes it on shutdown only if it still describes this server.
- Tool descriptions omit generated input-parameter and body-property prose already present in the input schema.
  FastMCP's formatter preserves authored descriptions, body-wide guidance and response documentation; schemas are unchanged.

## Settings

- `/exts/lightspeed.trex.mcp.core/host`: host to bind, default `127.0.0.1`.
- `/exts/lightspeed.trex.mcp.core/port`: preferred port, default `18014`.
- `/exts/lightspeed.trex.mcp.core/allow_port_range`: allow fallback within ports `18014–18019`, default `true`.
- `/exts/lightspeed.trex.mcp.core/log_level`: FastMCP server log level, default `warning`.
- `/exts/lightspeed.trex.mcp.core/transport`: MCP transport, `streamable-http` (default, served at `/mcp`) or
  `sse` (legacy, served at `/sse`). An unsupported value logs a warning and falls back to `streamable-http`.

FastMCP mounts the Streamable HTTP endpoint at `/mcp/`, so requests to `/mcp` answer with a 307 redirect that
preserves the method and body. Clients that do not follow redirects must be pointed at `/mcp/` directly.

Both the windowed Toolkit and the headless app prefer port `18014`. The configured port is tried first,
even if it is outside `18014–18019`. With fallback enabled, the server then tries ports `18014–18019`
in order, skipping the already-tried preferred port. With fallback disabled, only the configured port
is tried. If no candidate is available, MCP startup logs an error and stops.
On Windows, the listener uses exclusive address ownership so another Toolkit instance cannot
share its port and receive connections intended for it.

When fallback occurs, the `MCP_PORT_FALLBACK` warning records the requested port, selected port and
`endpoint=http://...` URL. Update the client's server URL to that endpoint, then wait for
`SERVICE_READY service=mcp` with the matching host and port to confirm it is accepting connections.
Client configuration files are not updated automatically.

The `sse` transport is the protocol's legacy HTTP transport, kept only for clients that cannot yet speak
Streamable HTTP.

## Discovery manifest

On Windows, every successful MCP listener publishes `%LOCALAPPDATA%\NVIDIA\RTX Remix\mcp.json`,
including after port fallback. For example:

```json
{
  "mcp_endpoint": "http://127.0.0.1:18014/mcp/",
  "rest_endpoint": "http://127.0.0.1:8011",
  "port": 18014,
  "rest_port": 8011,
  "version": "<running Toolkit version>",
  "pid": 12345
}
```

All six values come from the running app. The MCP URL ends in `/mcp/` for Streamable HTTP to
avoid a redirect, or `/sse` for the legacy transport. Publication is atomic and the file's ACL
allows only the current user. The most recent successful publication replaces the previous
instance's record; clean shutdown removes the file only if it still belongs to that instance.
Wildcard bind addresses `0.0.0.0` and `::` are advertised as the local connection addresses
`127.0.0.1` and `[::1]` in the manifest and fallback URLs; the listener's bind address stays unchanged.

A crash can leave a stale record. Check that `pid` is running and confirm the matching
`SERVICE_READY service=mcp` log or endpoint readiness before connecting. If publication fails,
the server logs a warning and continues; use the existing endpoint logs instead. Non-Windows
hosts use those logs without a discovery file. Client configurations are not rewritten.

## Protocol Version

The negotiated MCP protocol revision comes from the `mcp` SDK in the Flux pip prebundle, not from this extension.
The bundled SDK supports `2024-11-05`, `2025-03-26`, `2025-06-18`, and `2025-11-25`; a client that asks for a newer
revision negotiates down to `2025-11-25` rather than failing.

## Known limitations

- The OpenAPI spec is read once at startup. FastAPI caches `app.openapi()`, so a REST route
  registered by an extension that starts after the MCP server will not appear as a tool until
  the Toolkit restarts.
