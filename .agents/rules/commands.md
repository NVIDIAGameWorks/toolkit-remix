## Command Dispatch

When you recognize that you are about to perform one of these operations, read the corresponding file first and follow
its steps exactly. Do not invent an ad-hoc process.

## Git Rebase Safety

- Never use `git rebase -i` unless the user explicitly asks for an interactive rebase.
- Never run plain `git rebase --continue` in this repo. Continue rebases non-interactively so Git does not open an
  editor and block the agent.
- Use a no-op editor when continuing a rebase, for example:

```powershell
$env:GIT_EDITOR='py -3 -c "import sys; sys.exit(0)"'
git rebase --continue
```

- If you need a one-shot form, this is also acceptable:

```powershell
git -c core.editor=true rebase --continue
```

### Commands (multi-step procedures)

| When you are about to...             | Read and follow                            |
|--------------------------------------|--------------------------------------------|
| Create a feature branch              | `.agents/commands/create-branch.md`        |
| Commit changes                       | `.agents/commands/commit.md`               |
| Prepare a merge request              | `.agents/commands/prepare-mr.md`           |
| Scaffold a new extension             | `.agents/commands/create-extension.md`     |
| Remove an extension                  | `.agents/commands/remove-extension.md`     |
| Bump versions and update changelogs  | `.agents/commands/bump-exts-changelog.md`  |
| Diagnose an extension load failure   | `.agents/commands/debug-extension-load.md` |
| Update RTX Remix target dependencies | `.agents/commands/update-remix-deps.md`    |
| Add a pip package dependency         | `.agents/commands/add-pip-dep.md`          |
| Run or debug extension tests         | `.agents/commands/kit-test.md`             |

### Pattern guides (read before implementing)

| When you are about to...                    | Read first                                |
|---------------------------------------------|-------------------------------------------|
| Implement an undoable user action (command) | `docs_dev/patterns/commands.md`           |
| Add a REST service endpoint                 | `docs_dev/patterns/services.md`           |
| Add a Stage Manager plugin                  | `docs_dev/patterns/stage-manager.md`      |
| Add a validation/ingestion plugin           | `docs_dev/patterns/ingestion-pipeline.md` |
| Build UI components                         | `docs_dev/patterns/ui-style.md`           |
| Use a third-party pip package               | `docs_dev/patterns/pip-packages.md`       |

You do not need the user to type a slash command. If the user says anything equivalent to one of the operations above,
recognize it, load the file, and follow it.
