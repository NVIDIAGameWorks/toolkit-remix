## What This Is

The **NVIDIA RTX Remix Toolkit** (`lightspeed-kit`) is an Omniverse Kit SDK application for modding classic DirectX 8/9
games with RTX remastering. Monorepo with ~190 Omniverse extensions in two namespaces:

- **`lightspeed.*` / `lightspeed.trex.*`** — RTX Remix-specific logic (use for Remix-specific behavior)
- **`omni.flux.*`** — Generic, reusable Flux components (use for anything reusable across projects)

All source: `source/extensions/`. App definitions: `source/apps/`.

## Build, Run & Test

Full command reference: `docs_dev/tools/repo-tools.md`, `docs_dev/code-quality/testing.md`

**NEVER add extra flags to build, run, or test commands** unless the user explicitly asks. No `--no-window`,
no `--/app/extensions/registryEnabled=0`, no `--/app/auto_load_usd=""`. Run bat files exactly as-is.
The user needs to see and interact with the app window.

**Platform note:** commands below show Windows (`.bat`). On Linux/macOS, use the `.sh` equivalents
(`./build.sh`, `./format_code.sh`, `./lint_code.sh`) and replace `_build\windows-x86_64` with `_build/linux-x86_64`.

| Action               | Command (Windows)                                                    |
|----------------------|----------------------------------------------------------------------|
| Build                | `.\build.bat`                                                        |
| Run app (StageCraft) | `.\_build\windows-x86_64\release\lightspeed.app.trex.stagecraft.bat` |
| Run app (full)       | `.\_build\windows-x86_64\release\lightspeed.app.trex.bat`            |
| Test extension       | `.\_build\windows-x86_64\release\tests-<extension.name>.bat`         |
| Format               | `.\format_code.bat 2>&1 \| tail -30`                                 |
| Format (check only)  | `.\format_code.bat --check 2>&1 \| tail -30`                        |
| Lint                 | `.\lint_code.bat all 2>&1 \| tail -30`                               |
| List changed         | `python tools/utils/list_changed_exts.py`                            |

Test output: `_testoutput/exttest_<sanitized_name>/` (dots → underscores). Default timeout: 300 s.

**Running format/lint:** Run scripts directly (not via `cmd.exe /c`). The `| tail -30` in the commands above is
mandatory — these scripts emit thousands of file-listing lines that flood the context window without it.

**Lint caveat:** The `repo_lint` summary may report "0 errors" even when unfixable errors remain. Always check
the ruff output for `Found X errors (Y fixed, Z remaining)` — the summary line alone is **not reliable**.

When running the app, use `run_in_background=true` so you can continue responding while the user interacts with
the window. Watch logs for `[Error]` lines related to your changes.

## MCP Servers

Consult these **before** implementing anything that touches USD, Kit SDK, or `omni.ui`. Do not guess at API shapes from
memory.

| Server         | Use for                                                                             |
|----------------|-------------------------------------------------------------------------------------|
| `usd-code-mcp` | USD attribute names, schema types, `Usd.Stage` / `Usd.Prim` API, code generation    |
| `kit-dev-mcp`  | Omniverse Kit SDK APIs, `carb`, `omni.kit.*`, extension lifecycle, settings         |
| `omni-ui-mcp`  | `omni.ui` widget constructors, style properties, layout containers, event callbacks |

MCP servers are configured in `.mcp.json` (project root, canonical) and mirrored to `.cursor/mcp.json`,
`.vscode/mcp.json` (Copilot), and `.windsurf/mcp.json` for tools that use tool-specific config files. Claude Code reads
`.mcp.json` directly via `enableAllProjectMcpServers`.
