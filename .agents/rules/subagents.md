## Subagent Dispatch

**You MUST delegate to a specialist subagent whenever the task matches any row below.** Do NOT handle these domains
yourself — the subagent has deeper context, MCP access patterns, and domain-specific checklists that you will miss.

If you catch yourself thinking "this is simple enough to do inline" — that is exactly when you must dispatch. Simple
tasks done without the right context produce subtle bugs.

### Dispatch Table

| When the task involves...                         | Subagent type      | Config                            |
|---------------------------------------------------|--------------------|-----------------------------------|
| Writing or updating documentation                 | `docs`             | `.agents/subagents/docs.md`       |
| Writing unit tests                                | `unit-test-writer` | `.agents/subagents/unit-tests.md` |
| Writing E2E tests                                 | `e2e-test-writer`  | `.agents/subagents/e2e-tests.md`  |
| Implementing or debugging USD / pxr operations    | `usd-expert`       | `.agents/subagents/usd-expert.md` |
| Building or fixing omni.ui interfaces             | `ui-expert`        | `.agents/subagents/ui-expert.md`  |
| Reviewing code or a merge request                 | `reviewer`         | `.agents/subagents/review.md`     |

### When to Dispatch (non-obvious cases)

Dispatch is not limited to the table above. Also dispatch when:

- **Any code touches `omni.ui`** — even a one-line style fix → `ui-expert`
- **Any code touches USD stage, prims, layers, or attributes** — even reads → `usd-expert`
- **After implementing any feature** — dispatch `unit-test-writer`, `docs`, and `reviewer` in parallel
- **After fixing a bug** — dispatch `unit-test-writer` (regression test) and `reviewer` in parallel
- **Before creating an MR** — dispatch `reviewer` to catch issues before the human reviewer does

### Research-First Mandate (applies to ALL subagents)

**Every subagent MUST research before implementing.** This means:

1. **Query MCP servers first** — `usd-code-mcp` for USD code, `omni-ui-mcp` for UI code, `kit-dev-mcp` for Kit SDK
   APIs, settings, and extension lifecycle. Do not guess API shapes from training data.
2. **Read relevant `docs_dev/` guides** — pattern guides, architecture docs, and code-quality standards that apply to
   the domain. The command dispatch table in `commands.md` links to specific guides.
3. **Search the codebase for existing patterns** — this repo has ~190 extensions. Reuse existing implementations rather
   than inventing new patterns. Use the Explore agent or Grep for broad searches.
4. **Only then implement** — with real API signatures, real project patterns, and real constraints.

Include this mandate in the subagent prompt when dispatching. Example:

```
Before implementing anything:
1. Query the relevant MCP servers (usd-code-mcp / omni-ui-mcp / kit-dev-mcp) for API docs
2. Read the relevant docs_dev/ pattern guides
3. Search the codebase for existing examples of this pattern
Then implement based on what you found.
```

### Parallel Dispatch

Dispatch in parallel when a task spans multiple independent domains. Common parallel patterns:

- **After feature implementation:** `unit-test-writer` + `docs` + `reviewer`
- **After bug fix:** `unit-test-writer` (regression test) + `reviewer`
- **Multi-domain feature:** `ui-expert` + `usd-expert` (if UI + USD work are independent)

Use a single message with multiple Agent tool calls to launch them concurrently.
