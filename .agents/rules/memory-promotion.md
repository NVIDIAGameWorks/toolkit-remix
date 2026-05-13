## Memory Promotion

Durable project knowledge -> repo docs/shared rules, not private memory only.

Before done, check stable pattern/correction/debug/setup/project rule. If yes, update canonical:

- `docs_dev/` for human developer docs and setup/debugging notes.
- `.agents/rules/` for behavior all agents must follow.
- `.agents/context/` for small always-loaded project facts.
- Extension `docs/README.md` for extension responsibilities or public behavior.
- `.agents/instructions.local.md` only for ignored machine-local setup.

Do not promote guesses, session notes, local paths, branch state, unverified obs. Useful but unconfirmed -> report
evidence gap. Shared hook watches only ignored `.agents/memory-promotion.local.json` or `AGENT_MEMORY_PROMOTION_DIRS`.
Mention promotion in summary; if none, say none needed.
