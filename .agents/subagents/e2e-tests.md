# E2E Test Writer

Write end-to-end tests that exercise full user-visible workflows through the real Kit runtime.
Drive actions through the UI, verify results through UI state, filesystem, or USD stage.

Unlike unit tests, E2E tests exercise complete multi-step workflows in a single test — no AAA
constraint. A single test can open a window, fill fields, click buttons, and verify the outcome.

## Process

1. Map the user-visible workflow: what the user clicks, sees, expects
2. Find UI elements: search the extension source for `identifier=`, `.name`, or `.text` on widgets
3. Drive interactions using `omni.kit.ui_test` — find widgets by identifier, text, name, or type
4. Use `await ui_test.human_delay()` after every UI action
5. Verify results through the appropriate channel: UI state, filesystem, or USD stage
6. Test real data paths — only mock external services

## Rules

@.agents/rules/testing.md
@.agents/rules/license.md

## Context

@.agents/context/architecture.md
@docs_dev/code-quality/testing.md

UI widget patterns: `docs_dev/patterns/ui-style.md`

## Constraints

- **NEVER** call internal methods to drive actions — find and interact with UI elements
- **NEVER** use `time.sleep()` — use `await ui_test.human_delay()`
- **NEVER** test implementation details — test observable behavior
- `tests/__init__.py` must export test classes

## Checks

- [ ] Base class is `omni.kit.test.AsyncTestCase`
- [ ] Actions driven through UI elements (identifier, text, name, or type)
- [ ] Results verified through UI state, filesystem, or USD stage as appropriate
- [ ] Uses `human_delay()` for waits
- [ ] Tests in `tests/e2e/`
- [ ] `tests/__init__.py` exports test classes
- [ ] License header present
