## Engineering Standards

Apply these standards whenever fixing bugs, implementing features, or writing any code. Read
`docs_dev/code-quality/engineering-standards.md` for full anti-patterns and smell tests.

**Core principle: fix the root cause — never paper over a problem.**

**Directives that change how you approach every problem:**

- Never apply a fix at the wrong layer (compensating for a core bug in a widget)
- Never swallow exceptions: `except Exception: pass` is always wrong
- Never add feature flags or bypasses to avoid fixing broken behavior
- Never modify vendored Kit extension code under `_build/**/extscache/` or similar — fix misbehavior via launch config, settings, env vars, `.kit` file changes, or the `omni.kit.app` extension manager. Edits there get wiped on the next build and hide the real invariant the ext expects
- If you need a `sleep` to make it work → the async/data flow is broken; fix that instead
- One component, one job — if a function needs "and" to describe it, split it
- Never use `hasattr()`/`getattr()` on types you control — narrow the type or define a protocol instead

Full anti-patterns and smell tests: `docs_dev/code-quality/engineering-standards.md`
