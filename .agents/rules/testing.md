## Testing Requirements

Apply to every feature implementation. Read `docs_dev/code-quality/testing.md` for full guidance on test structure,
naming, and anti-patterns.

**Directives that change the entire approach to implementing features:**

1. **Plan tests before writing code.** Use Plan mode first. The test plan must list specific behaviors by name (
   `test_job_is_cancelled_when_websocket_disconnects`, not "test cancellation"). Only proceed after the plan is
   approved.

2. **≥75% test coverage is a hard PR requirement** — measured against the extension's current code, not just new lines.

3. **Unit tests** (`tests/unit/`): method-level tests that cover all code paths (happy path, error cases, edge cases,
   invalid input). Inherit `omni.kit.test.AsyncTestCase`, mock all external deps, one behavior per test. Structure: *
   *Arrange → Act → Assert**, strictly in that order, **exactly one Act**. Never loop sections (no Arrange → Assert →
   Act → Assert). If two actions need testing, write two tests.

4. **E2E tests** (`tests/e2e/`): real Kit instance, real data, full user-visible workflows. Drive actions through UI
   widget identifiers, verify results through UI state — not by calling internal methods directly.

5. **Every `tests/__init__.py`** must export its test classes — an empty `__init__.py` means the runner finds nothing.

6. **NEVER skip tests.** Do not add `@unittest.skip` unless the user explicitly authorizes it. A failing test must be
   fixed, not skipped. If a test cannot be fixed, ask the user before skipping.

Full guidance: `docs_dev/code-quality/testing.md`
