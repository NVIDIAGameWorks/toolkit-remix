## Command Dispatch

Task match -> read `.agents/commands/<name>.md`; follow exactly. No ad-hoc flow; slash not needed.

Commands: branch `create-branch`; commit `commit`; MR `prepare-mr`; new extension `create-extension`; remove extension
`remove-extension`; versions/changelogs `bump-exts-changelog`; extension load/test discovery `debug-extension-load`; pip
dep `add-pip-dep`; Kit tests `kit-test`.

Before implementation read pattern docs: undoable command `docs_dev/patterns/commands.md`; REST
`docs_dev/patterns/services.md`; Stage Manager `docs_dev/patterns/stage-manager.md`; validation/ingestion
`docs_dev/patterns/ingestion-pipeline.md`; UI `docs_dev/patterns/ui-style.md`; pip `docs_dev/patterns/pip-packages.md`.

Rebase safety: no `git rebase -i` unless user asks. No plain `git rebase --continue`; avoid editor block:

```powershell
$env:GIT_EDITOR='cmd /c exit 0'
git rebase --continue
```

One-shot OK: `git -c core.editor=true rebase --continue`.

Internal workflow + `.agents/commands/internal/README.md` exists -> read before choosing command.
