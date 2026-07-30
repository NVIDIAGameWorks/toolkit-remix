## Completion Gates

Claim done only after applicable gates pass or user accepts exception.

- Code changed: run relevant extension test with `-n default`; fix failures.
- Python changed: run `.\format_code.bat`; stage formatting fixes.
- Python changed: run `.\lint_code.bat all`; inspect ruff `Found X errors (Y fixed, Z remaining)`, not summary.
- Extension changed: compare `config/extension.toml` with `origin/<base>` and set a version strictly greater than the
  published base version; default to patch +1 from `origin/<base>` unless the branch already has a higher intentional
  version. Append entry last in extension `docs/CHANGELOG.md` section. No Jira prefix in extension changelog.
- Any MR: ensure one concise root `CHANGELOG.md` entry exists for the branch under `## [Unreleased]`; append it as the
  last item in the correct section to preserve chronological order; never insert at the top or reorder existing entries.
  Jira prefix only if provided. Do not add new root changelog entries for follow-up commits on a branch that has not
  merged yet.
- Behavior, setup, or API changed: update the relevant `docs_dev/` page or extension `docs/README.md`.
- History rewrites, fixup commits, generated lock refreshes, and autosquash operations: rerun applicable format/lint
  checks before declaring the branch ready; do not rely solely on hooks.

Before done: summarize changed files, verification commands/results, known issues, accepted exceptions. Gate fails +
cannot fix -> report why; never silently skip.
