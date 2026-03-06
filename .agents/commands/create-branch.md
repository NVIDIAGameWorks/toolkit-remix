# create-branch

Creates a feature branch following the project's branching conventions.

See `docs_dev/getting-started/git-workflow.md` for branch naming and base branch rules.

**Arguments:** optional description of the work

## Steps

1. Check for uncommitted changes — warn if dirty, ask how to proceed (stash, commit, or abort).
2. `git fetch origin`
3. Ask the user for the base branch if not obvious from context. Default to `main`.
4. Generate a branch name using the conventions in the git workflow doc. Confirm with the user.
5. `git checkout -b <branch-name> origin/<base-branch>`
6. Confirm creation.
