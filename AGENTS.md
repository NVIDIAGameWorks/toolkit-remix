# AGENTS.md

OpenAI/Codex/Antigravity entry. Canonical context: `.agents/instructions.md`.

Read it first. It points to always-on rules + on-demand refs.

Commands in `.agents/commands/`:

- `add-pip-dep.md` - add pip dep
- `bump-exts-changelog.md` - bump ext versions/changelogs
- `commit.md` - commit with repo style
- `create-branch.md` - create feature branch
- `create-extension.md` - scaffold extension
- `crash-debug.md` - gather/classify RTX Remix Toolkit crash evidence
- `debug-extension-load.md` - debug load/test discovery
- `kit-test.md` - run/debug Kit tests
- `prepare-mr.md` - prep MR
- `remove-extension.md` - remove extension + refs

Skills in `.agents/skills/`:

`add-pip-dep`, `agent-config`, `bump-exts-changelog`, `commit`, `completion-gates`, `create-branch`,
`create-extension`, `crash-debug`, `debug-extension-load`, `documentation`, `extension-docs`, `kit-test`,
`memory-promotion`, `prepare-mr`, `remove-extension`.

Auto-use `completion-gates` before done. Auto-use `memory-promotion` when durable project knowledge appears.

Internal checkout? If `.agents/commands/internal/README.md` exists, read it for internal commands.

Subagents:

- `docs` -> `.agents/subagents/docs.md`
- `unit-test-writer` -> `.agents/subagents/unit-tests.md`
- `e2e-test-writer` -> `.agents/subagents/e2e-tests.md`
- `usd-expert` -> `.agents/subagents/usd-expert.md`
- `ui-expert` -> `.agents/subagents/ui-expert.md`
- `reviewer` -> `.agents/subagents/review.md`
