## Completion Gates

Claim done only after applicable gates pass or user accepts exception.

- Code changed: run relevant extension test with `-n default`; fix failures.
- Python changed: run `.\format_code.bat`; stage formatting fixes.
- Python changed: run `.\lint_code.bat all`; inspect ruff `Found X errors (Y fixed, Z remaining)`, not summary.
- Extension changed: bump `config/extension.toml` version and append entry last in extension `docs/CHANGELOG.md`
  section. No Jira prefix in extension changelog.
- Any MR: append one concise root `CHANGELOG.md` entry last under `## [Unreleased]`; Jira prefix only if provided.
- Behavior, setup, or API changed: update the relevant `docs_dev/` page or extension `docs/README.md`.

Before done: summarize changed files, verification commands/results, known issues, accepted exceptions. Gate fails +
cannot fix -> report why; never silently skip.
