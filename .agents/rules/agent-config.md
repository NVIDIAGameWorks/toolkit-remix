## Agent Config

`.agents/` = canonical agent source. Agent-specific files = thin refs/wrappers. No copied prose.

### Canonical Dirs

| Path | Meaning |
| --- | --- |
| `.agents/context/` | Project facts: overview, architecture, resources |
| `.agents/rules/` | Agent behavior rules |
| `.agents/commands/` | Multi-step workflows |
| `.agents/skills/*/SKILL.md` | Shared skill wrappers, direct `@.agents/...` refs |
| `.agents/subagents/` | Canonical specialist role prompts |
| `.agents/hooks/` | Portable hook targets only |
| `.agents/scripts/` | Portable helper launchers; not hooks |

### Tool Surfaces

| Tool | Repo files | Rule |
| --- | --- | --- |
| Claude | `CLAUDE.md`, `.claude/skills/`, `.claude/settings.json`, `.claude/agents/` | Thin refs to `.agents/`; permissions in settings |
| Codex | `AGENTS.md`, `.codex/config.toml`, `.codex/hooks.json`, `.codex/agents/` | Shared project config only; subagents point to `.agents/subagents/` |
| Cursor | `.cursor/rules/*.mdc`, `.cursor/hooks.json` | Rule wrappers only; no shared-skill duplicates unless verified |
| Copilot | `.github/copilot-instructions.md` | Minimal inline critical rules + `.agents/` pointer |
| Gemini/Antigravity | `GEMINI.md`, `AGENTS.md` | `.agents/` pointer + public command/subagent index |
| Windsurf | `.windsurf/rules/project.md` | Inline only must-load rules; link `.agents/` for rest |
| Cline | `.clinerules` | Include `.agents/instructions.md` |
| Aider | no repo file | User runs `aider --read .agents/instructions.md` |
| MCP | `.mcp.json` + mirrors named in `.agents/context/project.md` | `.mcp.json` canonical; mirrors stay synced |

### Cursor Rules

Always: `project`, `architecture`, `commands`, `completion-gates`, `memory-promotion`.
Python globs: `code-style`, `code-comments`, `license`, `engineering-standards`, `testing`.

### Skills

On-demand rules/commands -> `.agents/skills/*/SKILL.md`. Codex/Cursor use shared skills. Claude needs matching
`.claude/skills/*/SKILL.md` wrappers. Skill body = direct `@.agents/...` ref, not prose path instruction. Keep auto
model invocation on unless safety reason documented.

No `.cursor/skills/` duplicate for shared skills unless current Cursor build proves needed. If needed, add thin wrapper
and document reason here. Cursor skill discovery version-sensitive.

### Rules

- Add/rename/remove shared rule, command, context, skill, subagent, hook, or MCP -> update matching Tool Surfaces row and
  every direct ref.
- No duplication. If wrapper cannot import, keep inline minimum and point to `.agents/`.
- `.agents/` agent-agnostic. No Codex/Claude/Cursor/private state paths. Hook targets may take `--agent` only for
  output contract formatting.
- Local/private checks -> ignored local config, not shared hooks.
- Hook targets live in `.agents/hooks/`; helpers live in `.agents/scripts/`.
- All shared hook commands use one entrypoint: `.agents/scripts/run_packman_python.cmd`. It is a polyglot shim:
  POSIX shells run its first line and exec `tools/packman/python.sh`; Windows `cmd.exe` treats that line as a label
  and runs `tools\packman\python.bat`. Never use system `python`, `python3`, or `py`.
- Hook commands avoid temp Git aliases. Codex, Claude, and Cursor all call `.agents/scripts/run_packman_python.cmd`;
  tool-specific config may differ only in path syntax and arg-list syntax.
- Keep hook arguments as real argv tokens. Do not combine the script path and flags into one `args` item; use
  `--agent=<agent>` when one token is clearer.
- Stop hook runner: `.agents/hooks/run_stop_checks.py --agent=<codex|claude|cursor> <check>...`.
  Check scripts return `0`
  allow, `2` block + stderr. Runner remaps by agent: `claude` keeps exit `2` + stderr; `codex` exits `0` + JSON
  `decision:block`/`reason`; `cursor` exits `0` + JSON `followup_message`.
- Memory watch only via ignored `.agents/memory-promotion.local.json` or env vars; no private state hardcode.
- New rule -> `.agents/rules/`, Cursor wrapper if always/glob, shared + Claude skill if on-demand, wire
  `.agents/instructions.md`.
- New command -> `.agents/commands/`, shared skill, Claude skill, `AGENTS.md`. No `.claude/commands/` duplicate unless
  documented legacy-client need. Commands stay lean; omit generic knowledge.
- Internal command -> `.agents/commands/internal/` + internal README. Do not list in `AGENTS.md` or shared tables unless
  intentionally public.
- New subagent -> `.agents/subagents/`, `.claude/agents/<name>.md`, `.codex/agents/<name>.toml`, `AGENTS.md`,
  `GEMINI.md`. No `.cursor/agents/` unless verified need documented.
- `.codex/config.toml` tracked only for shared project settings: MCP + `[features] hooks = true`. Local trust,
  personal skill toggles, trusted projects -> user config or ignored `*.local.toml`.
- Permissions/trust boundaries are agent-specific, not `.agents/`; Claude permissions in `.claude/settings.json`.
- Plans/specs -> `docs/plans/` (gitignored). Not `docs/superpowers/`. If using new plan dir, ignore it first or Sphinx
  fails on unlinked docs.
