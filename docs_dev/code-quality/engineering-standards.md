# Engineering Standards

Standards for writing correct, maintainable code in the RTX Remix Toolkit. These are not style preferences — violating
them produces broken or unmaintainable code.

---

## Core Principle

**Fix the root cause. Never paper over a problem.**

When something doesn't work, the fix belongs at the source of the problem. A workaround applied at the wrong layer
creates two problems: the original one (still unfixed) and the workaround (now load-bearing).

---

## Anti-Patterns

Never do these:

| Anti-pattern                                                                  | Why it's wrong                                                            |
|-------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| Apply a fix in the wrong layer (e.g. compensating for a core bug in a widget) | Hides the root cause; makes the widget brittle and unpredictable          |
| Widen tolerances or add retries to hide flaky behavior                        | The flakiness is the bug; you've just made it less visible                |
| Swallow exceptions silently: `except Exception: pass`                         | Turns a crash into a silent corruption or hang                            |
| Add a feature flag or code path bypass to avoid fixing broken behavior        | You now maintain two code paths; the broken one never gets fixed          |
| Leave dead code, legacy fallbacks, or half-completed migrations               | Future readers can't tell what's intentional; creates confusion and drift |
| Write 200+ line functions                                                     | No single function should need that much explanation — split it           |

---

## Design Rules

- **One component, one job.** If describing a function requires "and", split it.
- **The component that *creates* the problem owns the fix.** Don't compensate at a higher layer.
- **Expose the minimum public surface consumers actually need.** Every additional public method is a contract to
  maintain.

---

## Smell Tests

Stop and rethink if you hit any of these:

| Smell                                                        | What it means                                                                   |
|--------------------------------------------------------------|---------------------------------------------------------------------------------|
| "It works if I add a `sleep`"                                | Broken async or data flow — something is racing                                 |
| "It works if I read from the widget instead of from storage" | State is out of sync between the UI and the backing store                       |
| "It passes alone but fails alongside other tests"            | Shared mutable state is leaking between tests                                   |
| "I need a flag to skip this code path"                       | Ask: why does that path run when it shouldn't? Fix the condition, not the path. |
