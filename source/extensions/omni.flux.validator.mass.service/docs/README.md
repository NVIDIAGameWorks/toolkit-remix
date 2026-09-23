# omni.flux.validator.mass.service

Provides REST endpoints for mass validation queue submission and schema progress updates.

## Responsibilities

- Register schema-specific queue endpoints and forward updates to the mass validation queue.
- Describe the JSON request fields used by REST clients and generated MCP tools.

## Non-Responsibilities

- Running validation plugins directly or implementing MCP transport.

## Architecture

`MassValidatorService` registers endpoints through `ServiceBase`. Queue submission uses `ManagerMassCore`;
schema updates notify the mass validation queue through `UpdateSchemaRequestModel`.

`PUT /mass-validator/schema` accepts the existing flat validation-schema JSON object and an optional
`queue_id` query parameter. `_ValidationSchemaRequest` describes its wire fields for OpenAPI while
`ValidationSchema` remains responsible for runtime plugin validation. Plugin dictionaries stay open
because their fields depend on the registered plugin; runtime callbacks are not part of the wire format.
