# prepare-mr

Prepares the current branch for a merge request by running all completion gates, then pushing and
creating the MR. Platform-agnostic — works with both GitHub and GitLab.

See `docs_dev/getting-started/git-workflow.md` for branching conventions and MR process.

**Arguments:** none (auto-detects changed extensions and branch info)

## Step 0 — Pre-flight

```bash
git branch --show-current && git status --short
```

- **On `main`?** Run `/create-branch` (`.agents/commands/create-branch.md`) first, then continue.
- **Dirty working tree?** Run `/commit` (`.agents/commands/commit.md`) to commit pending work first.
- **Determine target branch.** Infer from branch name (`dev/*` → parent `feature/*`, `feature/*` → `main`).
  If unclear, ask the user. Store for all subsequent steps.

## Step 1 — Completion Gates

Run every gate from `.agents/rules/completion-gates.md` in order:

1. **Format**: `.\format_code.bat` — if files change, stage them.
2. **Lint**: `.\lint_code.bat all` — if errors, fix and re-run.
3. **Version bump + changelogs**: Run `/bump-exts-changelog` (`.agents/commands/bump-exts-changelog.md`),
   using the **target branch** instead of `origin/main` for diff comparisons.
4. **Docs**: Check if any changed behavior needs doc updates.
5. **Tests**: Ask the user if they want to run tests for modified extensions before pushing.

If any gate produces changes, run `/commit` to commit them before proceeding.

## Step 2 — Push

```bash
git push -u origin $(git branch --show-current)
```

## Step 3 — Create MR/PR

Detect which CLI is available:

```bash
which gh 2>/dev/null && echo "github" || (which glab 2>/dev/null && echo "gitlab" || echo "none")
```

- **`gh`**: `gh pr create --base <target-branch> --title "<title>" --body "<body>"`
- **`glab`**: `glab mr create --target-branch <target-branch> --title "<title>" --description "<body>"`
- **Neither**: Print the push URL and tell the user to create the MR/PR manually.

The title and body should be derived from the root CHANGELOG.md entry and the list of modified extensions.

## Notes

- Do not force-push or amend commits unless the user explicitly asks.
- If a gate fails and cannot be fixed, report it — do not skip gates.
