## Testing Requirements

Non-trivial/risky feature work -> plan tests before impl. Use Plan mode/approval when supported or scope ambiguous. Details:
`docs_dev/code-quality/testing.md`.

- PR target: at least 75% measured coverage for the extension's current code.
- Test names: `test_<action>_<condition>_<expected_outcome>`; concrete behavior, not vague category.
- Unit tests: `tests/unit/`, inherit `omni.kit.test.AsyncTestCase`, mock external deps, cover happy/error/edge/invalid
  paths, one behavior per test, `# Arrange` -> `# Act` -> `# Assert`, exactly one Act, never interleave.
- Test run: direct ext BAT -> add `-- --no-window`; visible UI only on ask. `repo.toml` `repo_test` already headless.
- E2E tests: `tests/e2e/`, real Kit, real data, user-visible workflow via widget IDs, verify UI state, headless unless
  user asks visible UI.
- Test organization: one test file per source file; one test class per source class; trivial glue exception only.
- E2E: do not run processes in parallel locally. No static appearance/layout checks; prove workflow/behavior. Known
  fixture project -> explicit fixture layers/paths; no production discovery APIs unless discovery itself under test.
- Every `tests/__init__.py` must export its test classes.
- Never skip tests unless the user explicitly authorizes it.
