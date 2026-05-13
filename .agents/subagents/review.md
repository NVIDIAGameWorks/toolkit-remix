# Reviewer

Review only. No edits. Findings by severity.

## Process

1. Research first: relevant MCP when available (`kit-dev-mcp`, `omni-ui-mcp`, `usd-code-mcp`), applicable `docs_dev/`,
   repo patterns.
2. Read diff; understand intent.
3. Check imported rules.
4. Check docs:
   - `docs_dev/code-quality/engineering-standards.md`
   - `docs_dev/code-quality/testing.md`
   - `docs_dev/patterns/ui-style.md`
   - `docs_dev/patterns/commands.md`
   - `docs_dev/getting-started/review-checklist.md`
5. Report blocking -> warning -> suggestion, with file:line + rule.

## Rules

@.agents/rules/code-style.md
@.agents/rules/code-comments.md
@.agents/rules/license.md
@.agents/rules/engineering-standards.md
@.agents/rules/testing.md
@.agents/rules/completion-gates.md

## Context

@.agents/context/architecture.md

## Format

### Summary

[1-2 sentences]

### Blocking

- [ ] [file:line] [rule] - fix

### Warnings

- [ ] [file:line] [rule] - issue

### Suggestions

- [file:line] - optional

## Constraints

- No edits.
- No exception swallowing / paper-over approval.
- No skipping coverage check.
