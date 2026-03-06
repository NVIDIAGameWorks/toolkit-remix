# AGENTS.md

This file provides guidance to OpenAI Codex and other OpenAI agents when working with this repository.

Read `.agents/instructions.md` for complete project context (it imports all sub-files automatically).

Available shared commands in `.agents/commands/`:
- `add-pip-dep.md` — add a third-party pip package to the project
- `bump-exts-changelog.md` — bump versions and changelogs for all modified extensions
- `commit.md` — commit changes following project conventions
- `create-branch.md` — create a feature branch with proper naming
- `create-extension.md` — scaffold a new extension from scratch
- `debug-extension-load.md` — diagnose extension load and test discovery failures
- `kit-test.md` — run or debug extension tests
- `prepare-mr.md` — prepare a merge request with proper description
- `remove-extension.md` — safely remove an extension and all its references
- `update-remix-deps.md` — update RTX Remix target dependencies to latest

## Subagents

Specialized role instructions in `.agents/subagents/`. Read the matching file and follow its role when the task matches:

- `docs.md` — documentation writer
- `unit-tests.md` — unit test writer
- `e2e-tests.md` — E2E test writer
- `usd-expert.md` — USD implementation expert
- `ui-expert.md` — UI implementation expert (omni.ui)
- `review.md` — code reviewer
