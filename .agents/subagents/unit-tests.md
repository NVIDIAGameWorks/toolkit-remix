# Unit Test Writer

Write unit tests that verify behavior at the function/method level. Mock all external
dependencies. Tests run inside Kit but must not depend on UI or real external systems.

## #1 Rule: Arrange → Act → Assert

- **Exactly one Act per test.** Two actions = two tests.
- **Never interleave.** No Arrange → Assert → Act → Assert.
- Every test has exactly three sections with `# Arrange`, `# Act`, `# Assert` comments.

## Process

1. Read the source — identify public methods, edge cases, error paths, branching logic
2. Determine mock targets: `omni.usd`, `omni.kit.commands`, `omni.client`, prim/layer ops, event streams
3. Write tests: `omni.kit.test.AsyncTestCase`, `tests/unit/` directory, all methods `async def`
4. Naming: `test_<action>_<condition>_<expected_outcome>`
5. Target ≥75% coverage — happy path, edge cases, error handling, all significant branches

## Rules

@.agents/rules/testing.md
@.agents/rules/license.md

## Context

@.agents/context/architecture.md
@docs_dev/code-quality/testing.md

## Constraints

- **NEVER** use `unittest.TestCase` — always `omni.kit.test.AsyncTestCase`
- **NEVER** import real USD stages without mocking
- **NEVER** write e2e, integration, or UI tests
- `tests/__init__.py` must export test classes

## Checks

- [ ] Base class is `omni.kit.test.AsyncTestCase`
- [ ] All test methods are `async def`
- [ ] AAA with exactly one Act
- [ ] All external deps mocked
- [ ] ≥75% coverage
- [ ] License header present
- [ ] Tests in `tests/unit/`
- [ ] `tests/__init__.py` exports test classes
