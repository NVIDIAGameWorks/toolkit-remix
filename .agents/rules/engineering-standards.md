## Engineering Standards

Apply these standards whenever fixing bugs, implementing features, or writing any code. Read
`docs_dev/code-quality/engineering-standards.md` for full anti-patterns and smell tests.

**Core principle: fix the root cause — never paper over a problem.**

**Directives that change how you approach every problem:**

- Never apply a fix at the wrong layer (compensating for a core bug in a widget)
- Never swallow exceptions: `except Exception: pass` is always wrong
- Never add feature flags or bypasses to avoid fixing broken behavior
- If you need a `sleep` to make it work → the async/data flow is broken; fix that instead
- One component, one job — if a function needs "and" to describe it, split it

Full anti-patterns and smell tests: `docs_dev/code-quality/engineering-standards.md`
