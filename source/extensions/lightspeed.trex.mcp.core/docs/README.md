# lightspeed.trex.mcp.core

Provides the RTX Remix Toolkit MCP server. It exposes Toolkit REST APIs and registered prompts through a FastMCP HTTP endpoint.

## Responsibilities

- Start the FastMCP server for RTX Remix Toolkit on the configured transport.
- Mount the Toolkit REST API as MCP tools under the `remix` namespace.
- Register MCP prompts for Toolkit workflows.
- Validate the configured port and, when range fallback is enabled, retry startup on an available port if the initial server bind fails.
- Publish `SERVICE_READY service=mcp` after Uvicorn is accepting connections on the selected endpoint.
- Close active connections through Uvicorn's supported shutdown lifecycle.

## Non-Responsibilities

- Defining REST API routes. Those are owned by the Toolkit service extensions.
- Owning user-facing MCP UI. This extension provides the server core only.
- Managing external MCP clients after they connect to the server endpoint.

## Architecture

- `MCPCore` reads the extension settings, builds a FastMCP server from the active `omni.services.core` FastAPI app, mounts it into the supplied MCP instance, registers prompts, and starts the configured transport.
- `_ServiceReadyServer` publishes the timestamped readiness marker after Uvicorn startup, rather than after the long-running server exits.
- `MCPPrompts` registers prompt definitions used by the MCP server.

## Settings

- `/exts/lightspeed.trex.mcp.core/host`: host to bind, default `127.0.0.1`.
- `/exts/lightspeed.trex.mcp.core/port`: preferred port, default `8000`.
- `/exts/lightspeed.trex.mcp.core/allow_port_range`: allow fallback to another available port, default `true`.
- `/exts/lightspeed.trex.mcp.core/log_level`: FastMCP server log level, default `warning`.
- `/exts/lightspeed.trex.mcp.core/transport`: MCP transport, `streamable-http` (default, served at `/mcp`) or
  `sse` (legacy, served at `/sse`). An unsupported value logs a warning and falls back to `streamable-http`.

FastMCP mounts the Streamable HTTP endpoint at `/mcp/`, so requests to `/mcp` answer with a 307 redirect that
preserves the method and body. Clients that do not follow redirects must be pointed at `/mcp/` directly.

The `sse` transport is the protocol's legacy HTTP transport, kept only for clients that cannot yet speak
Streamable HTTP. It is deprecated and scheduled for removal.

## Protocol Version

The negotiated MCP protocol revision comes from the `mcp` SDK in the Flux pip prebundle, not from this extension.
The bundled SDK supports `2024-11-05`, `2025-03-26`, `2025-06-18`, and `2025-11-25`; a client that asks for a newer
revision negotiates down to `2025-11-25` rather than failing.

`2025-11-25` is the ceiling for any FastMCP-based server today, because every stable FastMCP release requires
`mcp<2.0` and every `mcp` 1.x release stops at `2025-11-25`. Reaching the `2026-07-28` revision needs FastMCP 4.x,
which is still a prerelease and pulls the reworked `mcp` 2.x plus its new `mcp-types` and `httpx2` dependencies.
Revisit the `fastmcp` pin in `deps/pip_flux.toml` once FastMCP 4.x is stable.
