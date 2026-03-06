---
trigger: always
---

# RTX Remix Toolkit — Windsurf Rules

Full project context lives in `.agents/`. **Read these files before working in this repo:**

- `.agents/instructions.md` — master index, imports all sub-documents
- `.agents/context/project.md` — build, run, test commands
- `.agents/context/architecture.md` — extension patterns, USD contexts
- `.agents/rules/` — always-apply rules (code style, testing, license, engineering standards)
- `.agents/commands/` — step-by-step procedures for common operations

When asked to perform an operation that has a matching command in `.agents/commands/`, read that command file and follow
its steps exactly.

## Critical Rules

- Every Python file must begin with the SPDX Apache-2.0 license header
- Never use lazy imports (imports inside functions)
- All user-facing data mutations must go through `omni.kit.commands.Command` with `do()` and `undo()`
- All new features require >=75% test coverage
- `extension.toml` dependencies must exactly match actual imports
- Widgets must be built on `omni.ui.Frame` or `omni.ui.Stack`, never `omni.ui.Window`
- Format: `.\format_code.bat` | Lint: `.\lint_code.bat all` | Build: `.\build.bat`
- Bump `config/extension.toml` version and `docs/CHANGELOG.md` for every modified extension
