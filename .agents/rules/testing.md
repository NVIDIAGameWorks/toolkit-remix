## Testing Requirements

Non-trivial/risky feature work -> plan tests before impl. Use Plan mode/approval when supported or scope ambiguous. Details:
`docs_dev/code-quality/testing.md`.

- PR target: at least 75% measured coverage for the extension's current code.
- Test names: `test_<action>_<condition>_<expected_outcome>`; concrete behavior, not vague category.
- Unit tests: `tests/unit/`, inherit `omni.kit.test.AsyncTestCase`, mock external deps, cover happy/error/edge/invalid
  paths, one behavior per test, `# Arrange` -> `# Act` -> `# Assert`, exactly one Act, never interleave.
- E2E tests: `tests/e2e/`, real Kit, real data, user-visible workflow via widget IDs, verify UI state. Do not run E2E
  processes in parallel locally.
- Every `tests/__init__.py` must export its test classes.
- Never skip tests unless the user explicitly authorizes it.
