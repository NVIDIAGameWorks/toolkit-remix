# prepare-mr

Prep MR/PR. Run gates, push, create/update MR. Ref: `docs_dev/getting-started/git-workflow.md`.

## Style

Caveman talk: terse, no filler. Keep contracts exact. Lose no facts.

## Step 0 - Pre-flight

```bash
git branch --show-current && git status --short
```

- On `main` -> run `.agents/commands/create-branch.md`.
- Dirty -> run `.agents/commands/commit.md`.
- Target branch: usually `main`; stacked/scoped work -> parent `feature/*`. If unclear, ask. Reuse target below.

## Step 1 - Gates

Run applicable `.agents/rules/completion-gates.md`:

1. Format: `.\format_code.bat`; stage fixes.
2. Lint: `.\lint_code.bat all`; inspect ruff `Found X errors (Y fixed, Z remaining)`.
3. Version/changelog: `.agents/commands/bump-exts-changelog.md`, diffed against target branch.
4. Docs: update changed behavior docs.
5. Tests: ask user before running modified extension tests.

Gate changes -> commit before continuing.

## Step 2 - Push

```bash
git push -u origin $(git branch --show-current)
```

## Step 3 - Create MR/PR

### Required MR Body

Every MR/PR description starts with these sections, in this order, before any template marker/checklist:

1. `## What`
2. `## Why`
3. `## How`
4. `## Test Coverage`

Do not replace this with `Summary`, `Validation`, or command logs. Mention only tests/coverage that help the reviewer
assess changed behavior. For GitLab, paste the stock template below `Please don't delete after this line` and only toggle
checkboxes there.

Detect CLI:

```bash
which gh 2>/dev/null && echo "github" || (which glab 2>/dev/null && echo "gitlab" || echo "none")
```

- `gh`: `gh pr create --base <target-branch> --title "<title>" --body "<body>"`.
- `glab`:
  - Body source: `.gitlab/merge_request_templates/Default.md`.
  - Body before `Please don't delete after this line`: use Required MR Body. Small patch -> small body.
  - `Test Coverage` section above marker: include actual measured percent from real `--coverage` report for modified
    extension(s). No percent -> not ready. If coverage run fails from unrelated baseline/log issues, keep real percent
    and state short failure reason.
  - Below marker: template-owned. Do not edit wording, append notes, or add coverage text. Only toggle checkboxes.
  - No validation dump. Mention only tests/coverage that help reviewer assess changed behavior. Keep command logs out.
  - Create:

    ```bash
    glab mr create --target-branch <target-branch> --title "<title>" --description "<body>" --draft --remove-source-branch=true --squash-before-merge=true
    ```

  - PowerShell desc update: write UTF-8 no-BOM file, then:

    ```bash
    glab api "projects/:fullpath/merge_requests/<iid>" -X PUT -F "description=@<path-to-utf8-no-bom-file>"
    ```

  - Avoid `glab mr update -d "<multiline>"` for large bodies. Avoid raw JSON `glab api --input` here.
  - Preserve non-versioned GitLab checks: merge method, pipeline rules, discussion resolution.
- No CLI: print push URL; user creates MR/PR.

Title/body from root changelog + modified exts.

## Notes

No force-push/amend unless user asks. Gate fail + cannot fix -> report; do not skip.
