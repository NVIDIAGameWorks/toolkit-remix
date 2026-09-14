## Testing Requirements

Non-trivial/risky feature work -> plan tests before impl. Use Plan mode/approval when supported or scope ambiguous. Details:
`docs_dev/code-quality/testing.md`.

- PR target: at least 75% measured coverage for the extension's current code.
- Test names: `test_<action>_<condition>_<expected_outcome>`; concrete behavior, not vague category.
- Unit tests: `tests/unit/`, inherit `omni.kit.test.AsyncTestCase`, mock external deps, cover happy/error/edge/invalid
  paths, one behavior per test, `# Arrange` -> `# Act` -> `# Assert`, exactly one Act, never interleave.
- Classify the executed boundary before checking structure: isolated logic is unit; real workflows through UI controls
  or public service APIs are E2E. Service/API tests belong in `tests/e2e/` and may use AAA.
- Unit tests must not create or drive live UI. UI-independent logic with mocked UI dependencies is valid unit coverage.
  Helpers, cleanup, and exception-assertion contexts do not themselves add Acts; each subtest has independent AAA.
- Expected exceptions use `self.assertRaises`/`self.assertRaisesRegex`, never manual flags.
- Test run: direct ext BAT -> add `-- --no-window`; visible UI only on ask. `repo.toml` `repo_test` already headless.
- E2E tests: `tests/e2e/`, real Kit, real data, actual UI or public service/API entry point; verify the workflow outcome
  through UI, API responses, USD, or filesystem state. Headless unless user asks visible UI. UI E2Es use widget IDs and
  narrative workflow comments, not Arrange/Act/Assert sections; service/API tests need no UI gestures.
- E2E must not replace workflow data or exercised components with mocks/fakes/stubs. A representative real in-memory
  stage is valid; a stage-independent workflow needs no stage. Only data-free interception of an irreversible external
  effect may replace its terminal boundary; verify the request after the real application path reaches it.
- Test organization: independently testable logic maps to one unit-test file per source file and one test class per
  source class. Rendered behavior needs E2E; mixed modules need both. Preserve the trivial-glue exception: existing
  shared-contract coverage can suffice for mechanical forwarding, without duplicate wiring tests.
- Tests must detect a concrete regression. Remove fully redundant coverage or consolidate substantial repeated
  mechanics only with evidence that coverage, isolation, and failure diagnosis survive; syntax similarity is not enough.
- E2E: do not run processes in parallel locally. No static appearance/layout checks; prove workflow/behavior. Known
  fixture project -> explicit fixture layers/paths; no production discovery APIs unless discovery itself under test.
- Every `tests/__init__.py` must export its test classes.
- Never skip tests unless the user explicitly authorizes it.
- Review only violations introduced or worsened by the delta; unrelated historical test debt remains out of scope.
  Detailed boundaries and evidence requirements: `docs_dev/code-quality/testing.md`.
