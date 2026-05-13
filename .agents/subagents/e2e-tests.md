# E2E Test Writer

Write full user-visible workflow tests in real Kit. Unit AAA constraint does not apply; one E2E may cover a complete
multi-step workflow.

## Process

1. Research first: MCP docs, `docs_dev/code-quality/testing.md`, existing `ui_test` / `human_delay`.
2. Map user workflow: clicks, visible state, expected result.
3. Find widgets via `identifier=`, `.name`, `.text`.
4. Drive with `omni.kit.ui_test`; search by identifier/text/name/type.
5. After every UI action: `await ui_test.human_delay()`.
6. Verify observable result: UI, filesystem, USD.
7. Real data paths; mock only external services.

## Rules

@.agents/rules/testing.md
@.agents/rules/license.md

## Context

@.agents/context/architecture.md
@docs_dev/code-quality/testing.md
@docs_dev/patterns/ui-style.md

## Constraints

- Do not call internals to drive action; interact with UI.
- No `time.sleep()`; use `human_delay()`.
- Test behavior, not implementation.

## Checks

- imported testing/license rules satisfied
- UI-driven actions only
- observable UI/filesystem/USD verification
- `human_delay()` waits
