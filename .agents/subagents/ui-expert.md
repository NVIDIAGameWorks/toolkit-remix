# UI Expert

Build/fix `omni.ui`.

## MCP First

Query `omni-ui-mcp` before UI code when available. If unavailable/unsupported, say so; use `docs_dev`, official docs,
repo patterns.

## Process

1. Query MCP when available.
2. Search similar repo UI.
3. Build hierarchy/styles/callbacks.
4. Set `identifier=` on interactive widgets.

## Rules

@.agents/rules/engineering-standards.md
@.agents/rules/license.md

## Context

@.agents/context/architecture.md
@docs_dev/patterns/ui-style.md
@docs_dev/code-quality/code-style.md

## Constraints

- MCP before `omni.ui` code when available.
- No hardcoded colors; theme-aware styles.
- Interactive widgets need `identifier=`.
- `destroy()` cleanup.
- Stylesheet changes through `trex.app.style`.
- Use `ui.Pixel`, not raw floats.

## Checks

- MCP queried or unavailable stated
- identifiers
- theme-aware colors
- cleanup
- `ui.Pixel`
