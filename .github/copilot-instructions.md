# GitHub Copilot Instructions — lightspeed-kit

Full project context lives in `.agents/`. **Always read these files before working in this repo:**

- `.agents/instructions.md` — master index, imports all sub-documents
- `.agents/context/architecture.md` — extension patterns, lifecycle, events, USD contexts
- `.agents/context/project.md` — build, run, test commands and project overview
- `.agents/context/resources.md` — MCP servers, web docs, codebase search patterns
- `.agents/rules/` — always-apply rules (code style, imports, testing, license, engineering standards)
- `.agents/commands/` — step-by-step procedures for common operations
- `docs_dev/` — full human-readable reference (architecture, extension guide, code style, build/test, engineering
  standards)

When asked to perform an operation that has a matching command in `.agents/commands/`, read that command file and follow
its steps exactly.

---

## Critical Rules (always apply — read even if you skip the rest)

**Every Python file must begin with the SPDX Apache-2.0 license header.** New files use the current year. Never change
the year on existing files.

**Never use lazy imports** (imports inside functions). If a circular dependency makes this tempting, fix the module
boundaries.

**All user-facing data mutations must go through `omni.kit.commands.Command`** with `do()` and `undo()`. Direct
mutations are rejected in review.

**All new features require ≥75% test coverage.** Plan the test cases before writing any implementation code.

**`extension.toml` dependencies must exactly match actual imports** — add missing, prune unused. Add
`"omni.flux.pip_archive" = {}` if the extension imports any third-party pip package.

**Widgets must be built on `omni.ui.Frame` or `omni.ui.Stack`, never `omni.ui.Window`.** Never define inline
stylesheets — styles belong in the app-level `.style` extension.

**Always pass `context_name` explicitly to USD operations.** Never assume the default context.

**Fix the root cause, never paper over.** Never apply a fix at the wrong layer, swallow exceptions, or add sleep/retry
to hide flaky behavior.

**Update documentation when adding features.** Developer-focused content goes in `docs_dev/`, user-facing content goes
in `docs/`.
