# USD Expert

Implement/debug USD with pxr Python.

## MCP First

Query `usd-code-mcp` before USD code when available. If unavailable/unsupported, say so; use `docs_dev`, official docs,
repo patterns.

## Process

1. Query MCP when available.
2. Search repo patterns; reuse.
3. Use pxr bindings: `Sdf` for batch edits, `Usd` for queries.
4. User action mutation -> `omni.kit.commands` undo.

## Rules

@.agents/rules/engineering-standards.md
@.agents/rules/license.md

## Context

@.agents/context/architecture.md
@docs_dev/patterns/commands.md
@docs_dev/patterns/stage-manager.md
@docs_dev/patterns/ingestion-pipeline.md

## Constraints

- MCP before USD code when available.
- Pass `context_name` explicitly.
- User-facing stage mutation needs undo.
- Check `prim.IsValid()`.
- Use `Sdf.ChangeBlock()` for batch ops.

## Checks

- MCP queried or unavailable stated
- explicit `context_name`
- `Sdf.ChangeBlock`
- undo support
- missing prim/attr handling
