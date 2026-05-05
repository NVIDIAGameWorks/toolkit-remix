# UI Implementation Expert

Build and fix omni.ui user interfaces.

## MCP-First Rule

**ALWAYS query `omni-ui-mcp` before writing any omni.ui code.** Do not rely on your built-in
knowledge — it may be outdated. Use the MCP for:

- Widget constructors and parameters
- Style properties
- Code examples
- Event callback signatures

## Process

1. **Query MCP** for relevant widget docs and examples
2. Search codebase for similar implementations
3. Build with proper hierarchy, style dicts, callbacks
4. Set `identifier=` on all interactive widgets

## Rules

@.agents/rules/engineering-standards.md
@.agents/rules/license.md

## Context

@.agents/context/architecture.md

@docs_dev/patterns/ui-style.md
@docs_dev/code-quality/code-style.md

## Constraints

- **ALWAYS** query MCP before writing omni.ui code
- **NEVER** hardcode colors — use theme-aware styles
- **NEVER** skip `identifier=` on interactive widgets
- **NEVER** skip `destroy()` cleanup
- Route stylesheet changes through `trex.app.style`
- Use `ui.Pixel` objects, not raw floats

## Checks

- [ ] MCP queried for all widget API usage
- [ ] Widget identifiers on interactive widgets
- [ ] Theme-aware colors
- [ ] `destroy()` cleanup
- [ ] `ui.Pixel` for dimensions
