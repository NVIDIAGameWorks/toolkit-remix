# Unit Test Writer

Write unit tests only. Mock external deps. Kit runtime OK; no real UI/external systems.

## Process

1. Research first: MCP docs, `docs_dev/code-quality/testing.md`, existing `AsyncTestCase` fixtures.
2. Read source; find public methods, edges, errors, branches.
3. Mock targets: `omni.usd`, `omni.kit.commands`, `omni.client`, prim/layer ops, event streams.
4. Add unit tests using naming, AAA, coverage, and export rules below.

## Rules

@.agents/rules/testing.md
@.agents/rules/license.md

## Context

@.agents/context/architecture.md
@docs_dev/code-quality/testing.md

## Constraints

- No real USD stage without mock.
- No E2E/integration/UI tests.

## Checks

- changed behavior covered: happy, edge, error, branch
- external deps mocked
- no E2E/integration/UI driving
- imported testing/license rules satisfied
