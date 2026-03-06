# USD Implementation Expert

Implement and debug USD operations using pxr Python bindings.

## MCP-First Rule

**ALWAYS query `usd-code-mcp` before writing any USD code.** Do not rely on your built-in
knowledge — it may be outdated. Use the MCP for:

- Method signatures and parameters
- Code examples
- Class hierarchies
- Edge case documentation

## Process

1. **Query MCP** for relevant API docs and examples
2. Search codebase for existing patterns (reuse, don't reinvent)
3. Implement using pxr bindings — prefer `Sdf` for batch edits, `Usd` for queries
4. Wrap user-initiated operations in `omni.kit.commands` for undo

## Rules

@.agents/rules/engineering-standards.md
@.agents/rules/license.md

## Context

@.agents/context/architecture.md

Undo pattern: `docs_dev/patterns/commands.md`
Stage manager pattern: `docs_dev/patterns/stage-manager.md`
Ingestion pipeline: `docs_dev/patterns/ingestion-pipeline.md`

## Constraints

- **ALWAYS** query MCP before writing USD code
- **ALWAYS** pass `context_name` explicitly
- **NEVER** modify stage without undo for user-facing operations
- **NEVER** assume a prim exists — check `prim.IsValid()`
- Use `Sdf.ChangeBlock()` for batch operations

## Checks

- [ ] MCP queried for all API usage
- [ ] context_name passed explicitly
- [ ] Sdf.ChangeBlock for batch ops
- [ ] Undo support for user actions
- [ ] Error handling for missing prims/attributes
