# AI-Assisted Development

This project ships first-class support for AI coding agents. A shared instruction set in `.agents/` drives every
supported tool — Claude Code, Cursor, GitHub Copilot, Windsurf, Cline, Gemini CLI, Google Antigravity, and OpenAI
Codex — so all agents follow the same rules, patterns, and commands regardless of which editor you use.

---

## Best Practices

### Context Management

AI agent sessions degrade when the context window fills up — the model loses track of earlier details and responses
become less accurate. Most agents support some form of context compaction (Claude Code uses `/compact`, Cursor uses
`/summarize`). The principle is the same regardless of tool: **compact early, compact often.**

This project's Claude Code config demonstrates this with two safety nets, but the reasoning applies to any agent:

1. **Auto-compact at 80%** — when context usage hits 80%, the agent automatically compresses the conversation history.
   This is a hard safety net.

2. **Manual compact at 50%** — the recommended practice: **compact when you're roughly halfway through the context
   window.** Compacting at 50% preserves more useful context in the summary than waiting for the auto-compact threshold,
   because the model has more room to write a thorough summary. Waiting until 80% means the summary must be more
   aggressive, losing detail.

**Why 50% matters:** After compaction, the agent replaces the full conversation with a compressed summary. The earlier
you compact, the higher-quality that summary is — you retain more architectural decisions, debugging context, and
in-progress reasoning.

**Practical workflow:**

- Watch for context usage indicators (Cursor's token counter, etc.)
- At roughly 50% usage, look for a natural pause point and compact
- If you're mid-task with no good break point, it's fine to continue — the auto-compact safety net will catch you
- After compacting, briefly re-state any critical context the agent should keep in mind

### One Task per Session

Avoid cramming multiple unrelated tasks into a single agent session. Each task accumulates context — file reads, edits,
tool output — and mixing concerns makes the conversation harder to summarize and easier to confuse. Start a fresh
session for each distinct task (bug fix, feature, refactor). If a task naturally branches, that's a good signal to
compact or start fresh.

### Let the Agent Use Commands

You don't need to memorize slash commands. Describe what you want naturally — "scaffold a new extension", "bump versions
for my changes", "run the tests for this extension" — and the agent will auto-dispatch the right command from
`.agents/commands/`. The slash command syntax (`/create-extension`, `/kit-test`, etc.) is a shortcut, not a requirement.

### Recommended Plugins and Skills

Use these plugins and skills to cut token use and keep agent work focused on code, tests, and review instead of filler
or raw log noise:

| Plugin/skill | Use |
|--------------|-----|
| Superpowers | Workflow skills for planning, debugging, TDD, review, and verification when the task warrants the extra structure. |
| Ponytail | Keeps scope small: prefer existing repo patterns, standard tools, and the smallest correct diff. Install the plugin; no repo wiring is required. |
| Caveman | Forces terse agent responses while preserving exact code, commands, and technical terms. Install/configure it user-locally; this repo does not enable terse mode by default. |
| tokf | Filters verbose command output before it reaches the agent. Keep normal repo commands; the repo-local `.tokf` rewrites and filters make `build.bat`, `build_docs.bat`, `format_code.bat`, `lint_code.bat`, `repo.bat` subcommands, Kit tests, and Toolkit app BAT launches plug-and-play. |

`tokf raw last` can expose full unfiltered command output; scrub it before sharing when commands may include tokens or
service arguments.

### Inject Dynamic Context (Claude Code only)

Use `` !`command` `` in your Claude Code prompt to inject the output of a shell command directly into the message. This
gives the agent real-time context without a separate tool call. For example:

- `` /commit !`git diff` `` — runs the commit command with the current diff already in context
- `` Fix the errors in !`git diff --name-only` `` — tells the agent which files changed
- `` Explain !`git log --oneline -5` `` — feeds recent commit history into the prompt

This syntax is not available in Cursor or other agents at the moment.

---

## Supported Agents

| Agent                  | Entry point                       | Import mechanism                                       |
|------------------------|-----------------------------------|--------------------------------------------------------|
| **Claude Code**        | `CLAUDE.md`                       | `@.agents/instructions.md`                             |
| **Cursor**             | `.cursor/rules/*.mdc`             | Thin wrappers with `@.agents/...` imports              |
| **GitHub Copilot**     | `.github/copilot-instructions.md` | Critical rules inline + pointers to `.agents/`         |
| **Windsurf**           | `.windsurf/rules/project.md`      | Critical rules inline (6K char/file limit, no imports) |
| **Cline**              | `.clinerules`                     | `!include .agents/instructions.md`                     |
| **Gemini CLI**         | `GEMINI.md`                       | Thin pointer to `.agents/instructions.md`              |
| **Google Antigravity** | `GEMINI.md`                       | Shares entry point with Gemini CLI                     |
| **OpenAI Codex**       | `AGENTS.md`                       | Lists commands, points to `.agents/`                   |
| **Aider**              | *(no repo file)*                  | User runs `aider --read .agents/instructions.md`       |

Every agent gets the same project context, code-style rules, engineering standards, and commands. Differences are
limited to permission/trust boundaries (which live in each agent's own config) and import syntax.

---

## Primary Agent Surfaces

The Toolkit team primarily uses **Codex**, **Claude Code**, and **Cursor**. The exact maintenance protocol lives in
`.agents/rules/agent-config.md`; this page is the human overview.

| Surface                         | Purpose                                                                                  |
|---------------------------------|------------------------------------------------------------------------------------------|
| `.agents/instructions.md`       | Shared project instruction index                                                         |
| `.agents/context/`              | Shared project context and resource pointers                                             |
| `.agents/rules/`                | Canonical agent behavior rules                                                           |
| `.agents/commands/`             | Canonical multi-step procedures                                                          |
| `.agents/skills/`               | Shared Agent Skills wrappers that point to canonical commands or rules                   |
| `.agents/subagents/`            | Canonical specialist role instructions                                                   |
| `.agents/hooks/`                | Shared hook targets                                                                      |
| `.agents/scripts/`              | Portable helper launchers used by hooks or commands                                      |
| `AGENTS.md`                     | Codex, Antigravity, and other OpenAI-compatible entry point                               |
| `CLAUDE.md`                     | Claude Code entry point                                                                  |
| `.cursor/rules/`                | Cursor project rule wrappers                                                             |
| `.codex/`                       | Codex project config, hook config, and subagent wrappers                                  |
| `.claude/`                      | Claude Code project settings, skills, and subagent wrappers                              |
| `.cursor/hooks.json`            | Cursor hook config that invokes the shared `.agents/` hook targets                       |
| `.mcp.json` and mirrored config | Shared MCP server configuration                                                          |

Agent-specific files should stay thin. Put human-readable setup and rationale in `docs_dev/`; put agent behavior in
`.agents/`; put only the wrapper syntax required by each tool under `.codex/`, `.claude/`, or `.cursor/`.

### Commands and Skills

Full procedures live in `.agents/commands/`. These files are the source of truth for repeatable tasks such as creating
extensions, running Kit tests, committing, preparing MRs, adding pip dependencies, removing extensions, and bumping
extension changelogs.

Shared skill wrappers in `.agents/skills/` expose those procedures to tools that support Agent Skills. Claude Code has
matching `.claude/skills/` wrappers because Claude discovers project skills there. The wrappers should stay as aliases
to the canonical `.agents/` files; do not copy the procedure text into tool-specific folders.

Describe the operation naturally ("create an extension", "prepare an MR", "run this extension's tests") or use the
slash/skill command if your tool exposes one. If behavior needs to change, edit the `.agents/commands/` procedure or
the relevant `.agents/rules/` file first, then update wrappers only when discovery changes.

Internal-only procedures live under `.agents/commands/internal/` and are indexed from that directory's README. They are
not listed in the public command tables or shared skill discovery unless a tool needs a deliberate internal wrapper.

### Specialist Roles

Specialist role instructions live in `.agents/subagents/`. Use them when a task matches the domain: documentation,
unit tests, E2E tests, USD, omni.ui, or review. Claude Code and Codex have tool-specific subagent wrappers that point
back to the same canonical role files. Cursor does not get duplicate role files unless a verified Cursor requirement is
documented in `.agents/rules/agent-config.md`.

### Shared Hooks

Hooks run through one shared entrypoint: `.agents/scripts/run_packman_python.cmd`. The file is a polyglot shim: POSIX
shells run its first line and exec `tools/packman/python.sh`; Windows `cmd.exe` treats that line as a label and runs
`tools\packman\python.bat`. Codex, Claude Code, and Cursor all call the same shim; their config differs only in path
syntax and arg-list syntax. Keep hook args as argv tokens; do not combine the script path and flags into one argument.
Do not wrap hooks in Git aliases or call system Python.

The shared hook targets are:

| Hook target                               | Purpose                                                                                |
|-------------------------------------------|----------------------------------------------------------------------------------------|
| `.agents/hooks/run_stop_checks.py`        | Stop-hook runner; runs configured checks and formats failures per agent                 |
| `.agents/hooks/check_completion_gates.py` | Checks changed source Python files against formatting/lint completion expectations      |
| `.agents/hooks/check_memory_promotion.py` | Detects configured local memory changes that may need promotion to repo docs or rules   |

Tool-specific hook configuration stays in `.claude/settings.json`, `.codex/hooks.json`, and `.cursor/hooks.json`.
Those files should invoke shared `.agents/scripts/` launchers and `.agents/hooks/` targets instead of cloning logic.
Claude-specific permission prompts remain in `.claude/settings.json`; trust and approval policy is agent-specific and
does not belong in `.agents/`.

For workspace setup, recommended extensions, tasks, and debug config, see [VSCode / Cursor Setup](ide-vscode.md).

---

## Adding a New Agent

To add support for a new AI coding tool:

1. Create an entry-point file in the repo root or tool-specific directory
2. Import or reference `.agents/instructions.md` using the tool's native syntax
3. Add command wrappers if the tool supports slash commands
4. Add MCP server config if the tool supports MCP
5. Update `.agents/rules/agent-config.md` with the new entry
6. Update this page

See `.agents/rules/agent-config.md` for the full maintenance protocol.

---

## How It Works

### Shared Instruction Set (`.agents/`)

`.agents/` is the **single source of truth** for all agent instructions. Content is never duplicated across agent
configs — wrappers import from here.

| Directory           | Purpose                                                              |
|---------------------|----------------------------------------------------------------------|
| `.agents/context/`  | Project knowledge — always loaded. Describes what, how, and where.   |
| `.agents/rules/`    | Behavioral directives — always loaded or contextual. Constrains how. |
| `.agents/commands/` | Multi-step procedures — invoked by slash command or auto-dispatched. |
| `.agents/skills/`   | Agent Skills wrappers that expose shared commands and on-demand rules. |
| `.agents/subagents/` | Specialist role instructions shared through tool-specific wrappers.   |
| `.agents/hooks/`    | Hook targets used by Codex, Claude Code, and Cursor.                  |
| `.agents/scripts/`  | Portable helper launchers, including Packman Python runners.          |

`instructions.md` is the master index that imports everything. See `.agents/rules/agent-config.md` for the full
maintenance protocol (how to add rules, commands, and new agent wrappers).

### MCP Servers

Agents have access to Model Context Protocol servers that provide live API documentation and code search.

The MCP endpoints currently configured in this repo are NVIDIA-internal services. They may require NVIDIA network/VPN
access; external/public checkout users should expect those servers to be unavailable and use `docs_dev/`, official docs,
and repo patterns instead.

**`.mcp.json`** (project root) is the canonical MCP config. It follows the emerging cross-IDE standard and is read
directly by Claude Code (via `enableAllProjectMcpServers`). For tools that require their own config file, changes are
synced to:

| File                 | Tool           |
|----------------------|----------------|
| `.codex/config.toml` | Codex          |
| `.cursor/mcp.json`   | Cursor         |
| `.vscode/mcp.json`   | GitHub Copilot |
| `.windsurf/mcp.json` | Windsurf       |

When adding or removing an MCP server, edit `.mcp.json` first, then sync to the tool-specific files.
