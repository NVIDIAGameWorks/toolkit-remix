# Documentation Writer

Write and update documentation for lightspeed-kit.

## Where Content Belongs

- **`docs_dev/`** — developer-focused: architecture, patterns, build/test, code standards
- **`docs/`** — user-focused: UI guides, how-to articles, REST API reference, glossary
- **Extension `docs/README.md`** — per-extension docs (Responsibilities, Non-Responsibilities, Architecture)

## Process

1. Research first: use MCP docs to verify APIs/settings, read existing `docs/` and `docs_dev/`, and search the codebase
   for the actual implementation
2. Determine audience and correct tree
3. Update existing pages — only create new if nothing covers the topic
4. Cross-reference between trees, never duplicate content

## Rules

@.agents/rules/documentation.md
@.agents/rules/extension-docs.md

## Context

@.agents/context/architecture.md

## Checks

- [ ] Content in correct tree
- [ ] No duplication across trees
- [ ] Extension README has required sections
- [ ] Links use descriptive text and relative paths
