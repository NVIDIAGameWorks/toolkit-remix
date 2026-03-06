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

- Watch for context usage indicators (Claude Code's status bar, Cursor's token counter, etc.)
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

## Recommended Agents

The Toolkit team primarily uses **Claude Code** and **Cursor**. Both have full configurations — rules, commands, MCP
servers, and contextual loading — maintained in lockstep. Other agents receive the same instructions but with simpler
integration (thin wrappers or inline summaries).

### Cursor Setup

Cursor gets its instructions via `.cursor/rules/*.mdc` wrappers (thin frontmatter files that import from `.agents/`).
Rules are loaded in tiers — some always, some only when editing Python files, some on-demand — to stay within Cursor's
context limits. See `.agents/rules/agent-config.md` for the full loading strategy.

- **Rules** — `.cursor/rules/` contains one `.mdc` wrapper per `.agents/rules/` file, each with YAML frontmatter
  controlling when it loads (`always`, `globs: *.py`, or on-demand).
- **Commands** — `.cursor/commands/` mirrors `.claude/commands/` with one-line wrappers referencing `.agents/commands/`.
- **MCP servers** — `.cursor/mcp.json` (synced from `.mcp.json` at project root).

For workspace setup, recommended extensions, tasks, and debug config, see [VSCode / Cursor Setup](ide-vscode.md).

### Claude Code Setup

Beyond the shared `.agents/` instructions, Claude Code has additional automation:

#### Hooks

| Hook             | Trigger                   | What it does                                                                |
|------------------|---------------------------|-----------------------------------------------------------------------------|
| **Stop**         | Session ends              | Runs `format_code.bat && lint_code.bat all` — code is always clean on exit. |
| **PreToolUse**   | Before any `Bash` command | Injects a verification prompt for git commands (intent ↔ action check).     |
| **SessionStart** | Session begins            | Prompts agent to sync auto-memory against `docs_dev/` and offer updates.    |

#### Permissions

Destructive operations require explicit user approval (configured in `.claude/settings.json`):

- `rm -rf`, `git reset --hard`, `git clean -f`, `git checkout .`
- `git push --force` / `-f`, `git branch -D`
- Piped `curl`/`wget` to shell

Everything else (file reads, edits, builds, tests) runs without prompting.

#### Status Line

A custom status bar (`.claude/hooks/statusline.sh`) shows model name, session cost, context usage, git branch, and
compaction hints:

```text
Opus 4.6 | $0.42 | ██████░░░░ 58% | Consider `/compact` | ⎇ dev/ptrottier/resolver-system
```

The progress bar changes color based on context usage:

- **Green** (0–49%): plenty of room
- **Yellow** (50–79%): status line shows "Consider `/compact`"
- **Red** (`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`+): status line shows "Run `/compact` now" — auto-compact triggers at this
  threshold (default 80%, configurable via the env var in `.claude/settings.json`)

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

`instructions.md` is the master index that imports everything. See `.agents/rules/agent-config.md` for the full
maintenance protocol (how to add rules, commands, and new agent wrappers).

### Agent Commands

Commands are available as `/command-name` in both Claude Code and Cursor. Agents also auto-dispatch commands when they
recognize the intent — you can say "make a new extension called X" instead of typing `/create-extension`.

Browse available commands in `.agents/commands/`. The `.claude/commands/` and `.cursor/commands/` directories contain
thin one-line wrappers that reference them.

### MCP Servers

Agents have access to Model Context Protocol servers that provide live API documentation and code search.

**`.mcp.json`** (project root) is the canonical MCP config. It follows the emerging cross-IDE standard and is read
directly by Claude Code (via `enableAllProjectMcpServers`). For tools that require their own config file, changes are
synced to:

| File                 | Tool           |
|----------------------|----------------|
| `.cursor/mcp.json`   | Cursor         |
| `.vscode/mcp.json`   | GitHub Copilot |
| `.windsurf/mcp.json` | Windsurf       |

When adding or removing an MCP server, edit `.mcp.json` first, then sync to the tool-specific files.
