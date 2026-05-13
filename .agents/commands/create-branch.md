# create-branch

Create feature branch. Ref: `docs_dev/getting-started/git-workflow.md`. Arg: optional work description.

## Steps

1. Check dirty tree; if dirty, ask stash/commit/abort.
2. `git fetch origin`
3. Ask base if unclear; default `main`.
4. Generate branch name from git workflow doc; confirm.
5. `git checkout -b <branch-name> origin/<base-branch>`
6. Confirm branch.
