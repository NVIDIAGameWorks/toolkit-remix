# E2E Test Writer

Write real Kit workflows through UI controls or public service APIs. UI E2Es use narrative workflow comments;
service/API tests may use AAA. One E2E may cover a complete multi-step workflow.

## Process

1. Research first: MCP docs, `docs_dev/code-quality/testing.md`, existing `ui_test` / `human_delay`.
2. Map the workflow's public entry point and expected outcome.
3. For UI workflows, find widgets via `identifier=`, `.name`, `.text` and drive with `omni.kit.ui_test`.
4. For service/API workflows, exercise the live public API; follow `docs_dev/patterns/services.md`.
5. After every UI action: `await ui_test.human_delay()`.
6. Verify observable results: UI, API responses, filesystem, USD, including required state changes.
7. Use real workflow data and application components; do not mock them, including external service responses. Follow
   `docs_dev/code-quality/testing.md` -> Real E2E Data for the narrow terminal-effect interception exception.

## Rules

@.agents/rules/testing.md
@.agents/rules/license.md

## Context

@.agents/context/architecture.md
@docs_dev/code-quality/testing.md
@docs_dev/patterns/ui-style.md

## Constraints

- Do not call internals to drive the action; use the actual UI control or public service API.
- No `time.sleep()`; use `human_delay()` for UI waits.
- Test behavior, not implementation.

## Checks

- imported testing/license rules satisfied
- real public-entry-point actions and data
- observable UI/API/filesystem/USD verification
- `human_delay()` waits after UI actions
