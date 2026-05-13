# commit

Create well-formed commit. Ref: `docs_dev/getting-started/git-workflow.md`. Arg: optional message override.

## Steps

1. `git status --short`; `git diff --stat`; stop if no changes.
2. Ask what to stage: all, selected, or already staged.
3. `git diff --cached --stat`.
4. Inspect recent non-merge commits from current git user (`git config user.name`, `git config user.email`). Match that
   repo style. If no clear user history, use recent repo non-merge style. Conventional prefix only if dominant or user
   asks. Ask user confirm/edit message.
5. `git commit -m "<message>"`.
6. `git log --oneline -1 --stat`.

## Rules

No amend unless user asks. No `--no-verify`. Hook fail -> fix + retry new commit.
