# lightspeed.layer_manager.service

REST endpoints for project and layer management under `/layers`.

## Responsibilities

- Validate requests and expose layer operations through `LayerManagerService`.
- Return layer models for hierarchy, type-filtered, and immediate-sublayer queries in the configured USD context.

## Non-Responsibilities

Layer operations and response models belong to
[lightspeed.layer_manager.core](../../lightspeed.layer_manager.core/docs/README.md).
MCP tool generation belongs to `lightspeed.trex.mcp.core`.

## Architecture

`LayerManagerService` registers REST routes and delegates operations to `LayerManagerCore`.
The generated `remix_get_layers` and `remix_get_sublayers` MCP tools expose the same layer responses.
After `remix_mute_layer`, query layers and check the target layer's `muted` boolean to verify mute or unmute.
The field reports explicit mute state, as described in the core documentation above.

Layer-membership validation rejects requests with a 422 error when the configured USD context has no open stage,
before invoking the core operation. Open a project in that context before querying its sublayers.
