# prepare-mr

Run completion gates, push, create MR/PR. GitHub/GitLab. Ref: `docs_dev/getting-started/git-workflow.md`.

## Step 0 - Pre-flight

```bash
git branch --show-current && git status --short
```

- On `main` -> run `.agents/commands/create-branch.md`.
- Dirty -> run `.agents/commands/commit.md`.
- Target branch: usually `main`; use parent `feature/*` when stacked/scoped. If unclear, ask. Reuse target below.

## Step 1 - Gates

Run applicable `.agents/rules/completion-gates.md`:

1. Format: `.\format_code.bat`; stage changes.
2. Lint: `.\lint_code.bat all`; fix/rerun.
3. Version/changelog: `.agents/commands/bump-exts-changelog.md`, using target branch for diffs.
4. Docs: update changed behavior docs.
5. Tests: ask user before running modified extension tests.

Gate changes -> commit before continuing.

## Step 2 - Push

```bash
git push -u origin $(git branch --show-current)
```

## Step 3 - Create MR/PR

Detect CLI:

```bash
which gh 2>/dev/null && echo "github" || (which glab 2>/dev/null && echo "gitlab" || echo "none")
```

- `gh`: `gh pr create --base <target-branch> --title "<title>" --body "<body>"`
- `glab`:
  - Body source of truth: `.gitlab/merge_request_templates/Default.md`.
  - Prepend short summary, root changelog entry, modified exts, validation notes.
  - Include real measured `--coverage` percent for changed ext(s). If coverage run fails on unrelated baseline, keep
    real percent and state failure.
  - Create:

    ```bash
    glab mr create --target-branch <target-branch> --title "<title>" --description "<body>" --draft --remove-source-branch=true --squash-before-merge=true
    ```

  - PowerShell MR desc update: write UTF-8 no-BOM file, then:

    ```bash
    glab api "projects/:fullpath/merge_requests/<iid>" -X PUT -F "description=@<path-to-utf8-no-bom-file>"
    ```

  - Avoid `glab mr update -d "<multiline>"` for large bodies. Avoid raw JSON `glab api --input` here.
  - Preserve non-versioned GitLab checks: merge method, pipeline rules, discussion resolution.
- No CLI: print push URL; user creates MR/PR.

Title/body from root changelog + modified exts.

## Notes

No force-push/amend unless user asks. Gate fail + cannot fix -> report; do not skip.
