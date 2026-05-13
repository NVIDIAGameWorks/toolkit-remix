## Specialist Agents

If subagents available and work separable, delegate domain work. Small/tightly coupled work may stay local.

| Task | Specialist |
| --- | --- |
| Docs | `docs` |
| Unit tests | `unit-test-writer` |
| E2E tests | `e2e-test-writer` |
| USD / pxr | `usd-expert` |
| omni.ui | `ui-expert` |
| Review | `reviewer` |

Canonical roles: `.agents/subagents/`; wrappers point there.

Prefer delegate:

- Any `omni.ui` code -> `ui-expert`
- Any USD stage/prim/layer/attr code -> `usd-expert`
- After feature -> `unit-test-writer` + `docs` + `reviewer`
- After bug fix -> `unit-test-writer` regression + `reviewer`
- Before MR -> `reviewer`

Specialist prompt requires research first: relevant MCP if available, applicable `docs_dev/`, repo patterns, then implement.
Independent specialists -> one parallel multi-call when possible.
