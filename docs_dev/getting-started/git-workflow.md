# Git Workflow

Branching conventions, commit format, and merge request process for the RTX Remix Toolkit.

---

## Branch Naming

| Type              | Pattern                              | Example                                   |
|-------------------|--------------------------------------|-------------------------------------------|
| Feature branch    | `feature/<short-description>`        | `feature/comfyui-rework`                  |
| Dev sub-task      | `dev/<username>/<short-description>` | `dev/ptrottier/resolver-system`           |
| Bug fix           | `fix/<short-description>`            | `fix/event-stream-leak`                   |
| Dependency update | `dependabot/<description>`           | `dependabot/update-rtx-remix-target-deps` |

Derive `<username>` from `git config user.name` - lowercase, replace spaces with hyphens.

### One branch per change

Keep each branch focused on a single logical change. This keeps MRs small, easy to review, and atomic.

Everything that belongs to the same change - implementation, tests, documentation - stays on the same
branch. The goal is one *logical* change per branch, not one file per branch.

If you spot an unrelated bug or come up with another feature idea while working on something, resist
bundling it into the same branch. Create a separate branch and MR for it instead.

### Base branch

| Your branch      | Typical base                   |
|------------------|--------------------------------|
| `feature/*`      | `main`                         |
| `dev/*`, `fix/*` | A `feature/*` branch or `main` |

---

## Commit Format

Match the commit-subject style already used by the current Git user in this repository.

```
<subject line matching recent history>
```

Before choosing a message:

- Identify the current author from `git config user.name` and `git config user.email`.
- Inspect that user's recent **non-merge** commits in this repo.
- Match the dominant subject format, capitalization, and ticket-prefix usage from that history.
- If that user has no meaningful local history yet, fall back to recent non-merge commits in the repo.
- Use conventional-commit prefixes only if they are already the dominant style in the inspected history or the user
  explicitly asks for them.

Common patterns you may see in history:

- `<TICKET>: <summary>`
- `<Short summary without a type prefix>`

Rules:

- Summary: one line, max 72 characters, no trailing period
- Prefer the same tone and capitalization as the inspected history for that Git user
- Body is optional - use for context that the diff doesn't explain

---

## Merge Request Process

### Before creating the MR

1. **Format**: `.\format_code.bat`
2. **Lint**: `.\lint_code.bat all`
3. **Bump versions**: for each modified extension, bump `config/extension.toml` and add a changelog entry
   at the **end** of the appropriate section in `docs/CHANGELOG.md`
4. **Root changelog**: add a one-liner at the **end** of the appropriate section under `## [Unreleased]`
   in the root `CHANGELOG.md`. Prefix with Jira ticket: `REMIX-XXXX: <summary>`. Omit the prefix only if
   no ticket exists.
5. **Draft by default**: open the MR as Draft first, complete your self-review, then mark it ready.

### Repo-local GitLab defaults

- The canonical GitLab MR template lives in `.gitlab/merge_request_templates/Default.md`.
- If the repo-local template and the GitLab project-level default template ever conflict, prefer the repo-local file.
- When creating GitLab MRs with `glab`, pass `--draft --remove-source-branch=true --squash-before-merge=true`
  explicitly so the MR creation behavior matches the repo-local workflow.

### MR description

Include:

- Start from `.gitlab/merge_request_templates/Default.md`
- Summary of changes (from the root CHANGELOG entry)
- List of modified extensions
- Actual measured test coverage percentage from a real `--coverage` report for the modified extension(s)
- Known issues or follow-up work

Coverage guidance:

- Do not write "coverage" as a list of tests that exist. The MR must include the actual percentage from the generated
  coverage report.
- Run `.\repo.bat test -b <extension.name> --coverage` or
  `.\_build\windows-x86_64\release\tests-<extension.name>.bat -n default --coverage` and copy the reported percent.
- If the `--coverage` run still fails because of unrelated existing failures, keep the real reported percentage in the
  MR description and explicitly call out that the run failed plus the unrelated failing tests.

### Target branch

- `dev/*` branches -> target their parent `feature/*` branch
- `feature/*` branches -> target `main`
- If unclear, specify the target explicitly when creating the MR
