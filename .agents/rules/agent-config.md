## Agent Configuration

`.agents/` is the single source of truth for all AI agent instructions in this repo. Every agent-specific config file is
a thin wrapper that imports from here — never duplicate content across agent configs.

### Category definitions

| Category      | Purpose                                                                                                               | Location             |
|---------------|-----------------------------------------------------------------------------------------------------------------------|----------------------|
| **Rules**     | Behavioral directives — always-loaded or on-demand. Each rule constrains how agents write code.                       | `.agents/rules/`     |
| **Context**   | Project knowledge — always-loaded. Describes what the project is, how it's built, and where to find things.           | `.agents/context/`   |
| **Commands**  | Complex multi-step procedures — user-invoked or auto-dispatched when the agent recognizes the operation.              | `.agents/commands/`  |
| **Subagents** | Specialized role instructions — canonical content shared across all tools. Claude Code wrappers in `.claude/agents/`. | `.agents/subagents/` |

### What lives where

| File / directory                  | Purpose                                                                                                          |
|-----------------------------------|------------------------------------------------------------------------------------------------------------------|
| `.agents/context/`                | Canonical project knowledge (project overview, architecture, resources). Edit here.                              |
| `.agents/rules/`                  | Canonical behavioral rules. Edit here.                                                                           |
| `.agents/commands/`               | Canonical commands. Edit here.                                                                                   |
| `.agents/subagents/`              | Canonical subagent role instructions. Edit here. Shared by all tools.                                            |
| `.claude/agents/*.md`             | Claude Code + Cursor agent wrappers — frontmatter + `@.agents/subagents/<name>.md`.                              |
| `CLAUDE.md`                       | Claude Code entry point — imports `.agents/instructions.md`.                                                     |
| `AGENTS.md`                       | OpenAI Codex + Google Antigravity — lists available commands and points to `.agents/`.                           |
| `GEMINI.md`                       | Google Gemini CLI / Antigravity — thin pointer to `.agents/instructions.md`.                                     |
| `.github/copilot-instructions.md` | GitHub Copilot — critical rules inline; points to `.agents/` for full context.                                   |
| `.cursor/rules/*.mdc`             | Cursor rules — thin wrappers (`@.agents/rules/<name>.md` or `@.agents/context/<name>.md`) with frontmatter only. |
| `.cursor/skills/*/SKILL.md`       | Cursor skills — thin wrappers (`@.agents/commands/<name>.md` or `@.agents/rules/<name>.md`) with frontmatter.    |
| `.claude/commands/*.md`           | Claude Code slash commands — one-line wrappers (`@.agents/commands/<name>.md`).                                  |
| `.claude/settings.json`           | Claude Code permissions, hooks, plugins, output style.                                                           |
| `.mcp.json`                       | MCP servers (canonical). Read by Claude Code and any `.mcp.json`-aware tool.                                     |
| `.cursor/mcp.json`                | Cursor MCP servers (synced from `.mcp.json`).                                                                    |
| `.vscode/mcp.json`                | GitHub Copilot MCP servers (synced from `.mcp.json`).                                                            |
| `.windsurf/mcp.json`              | Windsurf MCP servers (synced from `.mcp.json`).                                                                  |
| `.windsurf/rules/project.md`      | Windsurf — critical rules inline; points to `.agents/` (6K char/file limit, no imports).                         |
| `.clinerules`                     | Cline — `!include .agents/instructions.md`.                                                                      |

### Cursor rules — loading strategy

| Rule                        | Loading       | Notes                                         |
|-----------------------------|---------------|-----------------------------------------------|
| `project.mdc`               | always        | Build/run/test commands                       |
| `architecture.mdc`          | always        | Extension design, USD contexts, lifecycle     |
| `commands.mdc`              | always        | Auto-dispatch agent commands + pattern guides |
| `completion-gates.mdc`      | always        | Pre-completion verification gates             |
| `code-style.mdc`            | globs: `*.py` | Formatting, imports, naming                   |
| `code-comments.mdc`         | globs: `*.py` | Docstring requirements                        |
| `license.mdc`               | globs: `*.py` | License headers for Python files              |
| `engineering-standards.mdc` | globs: `*.py` | Anti-patterns, root cause fixing              |
| `testing.mdc`               | globs: `*.py` | Coverage, AAA pattern, test naming            |

**always** = loaded into every conversation. **globs** = auto-loaded when working with matching files.

### Cursor skills — discovery strategy

On-demand rules and all commands are exposed as Cursor skills (`.cursor/skills/*/SKILL.md`). Each skill has a `name` and
`description` in its frontmatter; the body is an `@` reference to the canonical `.agents/` file. Cursor uses the
`description` to decide when to attach a skill to the conversation — make descriptions keyword-rich and action-oriented.

### Rules for maintaining this setup

- **Keep all agent configs in sync.** When you add, rename, or remove a rule, command, or context file, update every
  wrapper and entry point that references it. No agent should fall behind — if one agent gets an improvement, all agents
  get it. The agent entry points to keep in sync are:
    - **Claude Code**: `CLAUDE.md`, `.claude/commands/`, `.claude/settings.json`
    - **Cursor**: `.cursor/rules/*.mdc`, `.cursor/skills/*/SKILL.md`, `.cursor/mcp.json`
    - **MCP (all agents)**: `.mcp.json` → `.cursor/mcp.json`, `.vscode/mcp.json`, `.windsurf/mcp.json`
    - **GitHub Copilot**: `.github/copilot-instructions.md`, `.vscode/mcp.json`
    - **OpenAI Codex / Antigravity**: `AGENTS.md`
    - **Gemini CLI / Antigravity**: `GEMINI.md`
    - **Windsurf**: `.windsurf/rules/project.md`
    - **Cline**: `.clinerules`
    - **Aider**: no repo file — users run `aider --read .agents/instructions.md`
- **Never duplicate content.** `.agents/` is the single source of truth. Wrappers must import or reference `.agents/`
  files — never copy content into agent-specific files. If a wrapper can't import (e.g.
  `.github/copilot-instructions.md`),
  keep the inline portion minimal and point to `.agents/` for the full version.
- **Add new rules in `.agents/rules/`**, then create a wrapper in `.cursor/rules/` (for always-loaded or glob-based
  rules) or `.cursor/skills/` (for on-demand rules), and wire it into `.agents/instructions.md`. Do not write the rule
  inline in any agent-specific file.
- **Add new commands in `.agents/commands/`**, then create a skill in `.cursor/skills/<name>/SKILL.md` (with `name`,
  `description`, and `@.agents/commands/<name>.md`), a one-line wrapper in `.claude/commands/`, and add the entry to
  `AGENTS.md`. Keep commands lean and focused — only document information the model cannot reliably infer on its own.
  Do not add default knowledge (e.g. semver rules, git basics, general coding conventions).
- **Add new subagents in `.agents/subagents/`**, then create a wrapper in `.claude/agents/<name>.md` (with frontmatter
  and `@.agents/subagents/<name>.md`), and add the entry to `AGENTS.md` and `GEMINI.md`. Cursor discovers
  `.claude/agents/` natively — no separate skill needed.
- **MCP servers**: `.mcp.json` (project root) is the canonical source. Sync changes to `.cursor/mcp.json`,
  `.vscode/mcp.json` (Copilot), and `.windsurf/mcp.json`.
- **Permissions and trust boundaries** (what an agent may do autonomously vs. must ask about) belong in the
  agent-specific entry point, not in `.agents/`. Claude Code permissions live in `.claude/settings.json`.
- **Development plans and specs** must be saved to `docs/plans/` (already gitignored). Never save them to
  `docs/superpowers/` or any other location. If you use an alternative directory, add it to `.gitignore` before
  saving any files there — failing to do so will break the docs build (Sphinx treats unlinked files as errors).
