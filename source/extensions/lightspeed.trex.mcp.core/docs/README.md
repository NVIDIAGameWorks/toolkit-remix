# lightspeed.trex.mcp.core

Provides the RTX Remix Toolkit MCP server. It exposes Toolkit REST APIs and registered prompts through a FastMCP SSE endpoint.

## Responsibilities

- Start the FastMCP SSE server for RTX Remix Toolkit.
- Mount the Toolkit REST API as MCP tools under the `remix` namespace.
- Register MCP prompts for Toolkit workflows.
- Validate the configured port and, when range fallback is enabled, retry startup on an available port if the initial server bind fails.
- Publish `SERVICE_READY service=mcp` after Uvicorn is accepting connections on the selected endpoint.
- Close active connections through Uvicorn's supported shutdown lifecycle.

## Non-Responsibilities

- Defining REST API routes. Those are owned by the Toolkit service extensions.
- Owning user-facing MCP UI. This extension provides the server core only.
- Managing external MCP clients after they connect to the SSE endpoint.

## Architecture

- `MCPCore` reads the extension settings, builds a FastMCP server from the active `omni.services.core` FastAPI app, mounts it into the supplied MCP instance, registers prompts, and starts SSE transport.
- `_ServiceReadyServer` publishes the timestamped readiness marker after Uvicorn startup, rather than after the long-running server exits.
- `MCPPrompts` registers prompt definitions used by the MCP server.

## Settings

- `/exts/lightspeed.trex.mcp.core/host`: host to bind, default `127.0.0.1`.
- `/exts/lightspeed.trex.mcp.core/port`: preferred port, default `8000`.
- `/exts/lightspeed.trex.mcp.core/allow_port_range`: allow fallback to another available port, default `true`.
- `/exts/lightspeed.trex.mcp.core/log_level`: FastMCP server log level, default `warning`.
