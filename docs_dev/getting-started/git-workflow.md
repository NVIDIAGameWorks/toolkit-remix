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

Derive `<username>` from `git config user.name` — lowercase, replace spaces with hyphens.

### One branch per change

Keep each branch focused on a single logical change. This keeps MRs small, easy to review, and atomic.

Everything that belongs to the same change — implementation, tests, documentation — stays on the same
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

Use conventional commits:

```
<type>: <summary>
```

| Type       | When                                |
|------------|-------------------------------------|
| `feat`     | New functionality                   |
| `fix`      | Bug fix                             |
| `refactor` | Code change without behavior change |
| `chore`    | Config, CI, tooling, dependencies   |
| `docs`     | Documentation only                  |
| `test`     | Test additions or changes           |
| `style`    | Formatting, linting fixes           |

Rules:

- Summary: one line, max 72 characters, no trailing period
- Use imperative mood ("add X" not "added X")
- Body is optional — use for context that the diff doesn't explain

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

### MR description

Include:

- Summary of changes (from the root CHANGELOG entry)
- List of modified extensions
- Known issues or follow-up work

### Target branch

- `dev/*` branches → target their parent `feature/*` branch
- `feature/*` branches → target `main`
- If unclear, specify the target explicitly when creating the MR
