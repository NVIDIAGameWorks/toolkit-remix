## Subagent Dispatch

When a task falls into a specialized domain, delegate to the corresponding subagent.

| When the task involves...                | Subagent config                   |
|------------------------------------------|-----------------------------------|
| Writing or updating documentation        | `.agents/subagents/docs.md`       |
| Writing unit tests                       | `.agents/subagents/unit-tests.md` |
| Writing E2E tests                        | `.agents/subagents/e2e-tests.md`  |
| Implementing or debugging USD operations | `.agents/subagents/usd-expert.md` |
| Building or fixing omni.ui interfaces    | `.agents/subagents/ui-expert.md`  |
| Reviewing code or a merge request        | `.agents/subagents/review.md`     |

Dispatch in parallel when a task spans multiple independent domains (e.g., after implementing a
feature, dispatch unit-test-writer, docs, and reviewer simultaneously).
