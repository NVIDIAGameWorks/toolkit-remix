# commit

Creates a well-formed commit from current changes.

See `docs_dev/getting-started/git-workflow.md` for commit format conventions.

**Arguments:** optional commit message override

## Steps

1. `git status --short && git diff --stat` — show what changed. Stop if nothing to commit.
2. Ask the user what to stage (all, select files, or already staged).
3. `git diff --cached --stat` — confirm what will be committed.
4. Generate a conventional commit message from the staged diff. Infer the type from the changes. Ask
   the user to confirm or edit before committing.
5. `git commit -m "<message>"` — create the commit.
6. `git log --oneline -1 --stat` — show the result.

## Notes

- Never amend a previous commit unless the user explicitly asks.
- Never use `--no-verify` to skip hooks.
- If a pre-commit hook fails, fix the issue and retry with a new commit.
