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
- **`glab`**:
  1. Treat `.gitlab/merge_request_templates/Default.md` as the repo-local source of truth for the GitLab MR body.
     If the repo-local template and GitLab project settings ever diverge, prefer the repo-local file.
  2. Build the final MR description by prepending a short summary section (root `CHANGELOG.md` entry), the list of
     modified extensions, and test/validation notes to that template.
     The description must include the actual measured coverage percentage from a real `--coverage` report for the
     modified extension(s). Do not replace the percentage with a test list or a qualitative claim such as "tests were
     added". If the `--coverage` run still has unrelated baseline failures, keep the real percentage in the
     description and state clearly that the run failed and why.
  3. Create the MR with explicit repo-local defaults instead of relying on GitLab project defaults:

     ```bash
     glab mr create --target-branch <target-branch> --title "<title>" --description "<body>" --draft --remove-source-branch=true --squash-before-merge=true
     ```

  4. When updating an existing GitLab MR description from PowerShell, prefer:

     ```bash
     glab api "projects/:fullpath/merge_requests/<iid>" -X PUT -F "description=@<path-to-utf8-no-bom-file>"
     ```

     Do not rely on `glab mr update -d "<multiline body>"` for large multiline descriptions in PowerShell, and do not
     send a raw JSON body with `glab api --input` for this endpoint.

  5. Preserve any GitLab-enforced merge checks that cannot be versioned in-repo (for example, merge method, pipeline
     requirements, and discussion-resolution requirements).
- **Neither**: Print the push URL and tell the user to create the MR/PR manually.

The title and body should be derived from the root CHANGELOG.md entry and the list of modified extensions.

## Notes

- Do not force-push or amend commits unless the user explicitly asks.
- If a gate fails and cannot be fixed, report it — do not skip gates.
