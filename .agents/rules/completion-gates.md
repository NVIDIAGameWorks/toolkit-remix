## Completion Gates

Before declaring any implementation task done, verify your work. Do not claim completion until all applicable gates pass
or the user explicitly accepts exceptions.

**Gates (check every one that applies):**

1. **Tests pass** — if you wrote or modified code, run the extension's test bat with `-n default`. If tests fail, fix
   them before completing.
2. **Format is clean** — if you modified Python files, run `.\format_code.bat`. Always run the script locally — never
   assume formatting is clean based on CI output or prior runs. If it changes files, stage the formatting fixes.
3. **Lint is clean** — if you modified Python files, run `.\lint_code.bat all`. This checks **ALL files** in
   `source/extensions/`, not just modified ones. Fix any errors before completing — including pre-existing errors in
   files you did not modify. The codebase must have zero lint errors. Always run locally — never assume lint is clean
   based on CI output or prior runs. Check the full ruff output for `Found X errors (Y fixed, Z remaining)` — the
   `repo_lint` summary line may report 0 errors even when unfixable errors remain.
4. **Version bumped** — if you modified an extension, bump its version in `config/extension.toml` and add a changelog
   entry as the **last item** of the appropriate section in `docs/CHANGELOG.md`. Never insert at the top — always append
   after the last existing entry in that section.
5. **Root CHANGELOG.md updated** — once per MR, add a concise one-liner as the **last item** of the appropriate section
   under `## [Unreleased]` in the root `CHANGELOG.md`. Never insert at the top of a section — always append after the
   last existing entry. Always applies, including docs-only changes. Do not mention release versions. Follow existing
   entry style.
6. **Docs updated** — if you changed behavior, public API, or added a feature, update the relevant `docs_dev/` file or
   extension `docs/README.md`.

**Evidence — summarize before completing:**

- Changed files grouped by purpose
- Test command(s) run and their pass/fail status
- Any known issues, deferred work, or accepted exceptions

**If a gate fails and you cannot fix it**, report what failed and why. Do not silently skip gates.
