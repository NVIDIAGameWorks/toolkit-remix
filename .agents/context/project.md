## Project

RTX Remix Toolkit (`lightspeed-kit`) = Omniverse Kit SDK app for RTX-remastering classic DX8/9 games. ~190 ext:
`source/extensions/`; apps `source/apps/`; Remix `lightspeed.*` / `lightspeed.trex.*`; reusable Flux `omni.flux.*`.

## Build, Run, Test

Refs: commands `docs_dev/tools/repo-tools.md`; tests `docs_dev/code-quality/testing.md`.

Run scripts as-is. Tests: direct ext BAT -> add `-- --no-window`; visible UI only on ask. `repo.toml` `repo_test`
already headless. Non-test app scripts: no extra flags unless user asks; no `--no-window`,
`--/app/extensions/registryEnabled=0`, `--/app/auto_load_usd=""`. User may need visible app. Background ok; watch
relevant `[Error]`.
Run only full/dev app; no StageCraft/layout launchers unless user asks.

Use Packman Python only: never system `python`, `python3`, `py`.

Linux/macOS: `.sh` equivalents + `_build/linux-x86_64`. Python utilities: `tools/packman/python.bat` or
`tools/packman/python.sh`.

Format/lint direct; keep `tail -30`. Lint: inspect ruff `Found X errors (Y fixed, Z remaining)`, not only
`repo_lint` summary. Test output `_testoutput/exttest_<sanitized_name>/`; timeout 300s.

## MCP Servers

Before USD, Kit SDK, `omni.ui`: if matching MCP available, query it. Repo MCP endpoints are NVIDIA-internal/VPN. If
unavailable/unsupported, say so; use `docs_dev`, official docs, repo patterns. No API shape guessing.

Use: `usd-code-mcp` for USD attrs/schemas/`Usd.Stage`/`Usd.Prim`; `kit-dev-mcp` for Kit SDK/`carb`/`omni.kit.*`/
lifecycle/settings; `omni-ui-mcp` for `omni.ui` constructors/styles/layouts/events.

`.mcp.json` canonical. Mirror to `.codex/config.toml`, `.cursor/mcp.json`, `.vscode/mcp.json`, `.windsurf/mcp.json`.
Claude Code reads `.mcp.json` directly via `enableAllProjectMcpServers`.
