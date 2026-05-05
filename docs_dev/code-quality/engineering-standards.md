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

| Anti-pattern                                                                  | Why it's wrong                                                                          |
|-------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| Apply a fix in the wrong layer (e.g. compensating for a core bug in a widget) | Hides the root cause; makes the widget brittle and unpredictable                        |
| Widen tolerances or add retries to hide flaky behavior                        | The flakiness is the bug; you've just made it less visible                              |
| Swallow exceptions silently: `except Exception: pass`                         | Turns a crash into a silent corruption or hang                                          |
| Add a feature flag or code path bypass to avoid fixing broken behavior        | You now maintain two code paths; the broken one never gets fixed                        |
| Leave dead code, legacy fallbacks, or half-completed migrations               | Future readers can't tell what's intentional; creates confusion and drift               |
| Write 200+ line functions                                                     | No single function should need that much explanation — split it                         |
| Use `hasattr`/`getattr` to probe for attributes on your own typed objects     | Means the type hierarchy is wrong — fix the types, don't guess at runtime               |
| Suppress lint warnings with `# noqa` instead of fixing the code               | Fix the root cause — rename the variable, restructure the code, or remove the dead code |

---

## `hasattr` / `getattr` Policy

**Do not use `hasattr()` or `getattr()` to access attributes on objects whose types you control.** These calls
are a sign that the type signature is lying — the code claims to accept a base type but actually requires fields
from a subclass it refuses to name.

### What to do instead

| Situation                                                                                                                                                        | Solution                                                                                                                                                                                   |
|------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A method accepts a base class but accesses fields only defined on a subclass (e.g., `getattr(item, "path", "")` when `path` exists on `FileItem` but not `Item`) | Narrow the parameter type to the subclass and access the field directly. If the method only works with `FileItem`, type it as `FileItem`.                                                  |
| An override of an abstract method needs a more specific type than the base declares                                                                              | Use the concrete subclass type in the override. If the dispatch mechanism already guarantees the type (e.g., a registry or `isinstance` gate), the override signature should reflect that. |
| Multiple unrelated classes share an optional capability (e.g., some plugins have a `visible` property, others don't)                                             | Define a `typing.Protocol` (with `@runtime_checkable` if you need runtime checks) and use `isinstance()` instead of `hasattr()`.                                                           |
| A function operates on a base dataclass but needs fields from a specific subclass                                                                                | Type the parameter as the subclass directly. If the function must remain generic, make the class generic over a `TypeVar` bound to the base (e.g., `C = TypeVar("C", bound=BaseContext)`). |
| Iterating over `dataclasses.fields()` for generic comparison, serialization, or copy                                                                             | Acceptable — field names are guaranteed to exist by the dataclass definition. This is reflective metaprogramming, not attribute guessing.                                                  |
| Checking whether an external library exposes an API across versions (e.g., `hasattr(UsdLux, "LightAPI")`)                                                        | Acceptable — you don't control the external type and need version-portable code.                                                                                                           |

### Why this matters

- **Static analysis breaks.** Type checkers, IDE navigation, and refactoring tools cannot follow `getattr` calls.
- **Errors move to runtime.** A typo like `getattr(item, "pahts", [])` silently returns `[]` instead of failing at
  import time. With direct attribute access, the typo is caught immediately by the type checker and IDE.
- **Intent is hidden.** `getattr(item, "paths", [])` doesn't tell the reader *why* this field might be missing,
  which subclass types have it, or whether the fallback is actually expected.

---

## Design Rules

- **One component, one job.** If describing a function requires "and", split it.
- **The component that *creates* the problem owns the fix.** Don't compensate at a higher layer.
- **Expose the minimum public surface consumers actually need.** Every additional public method is a contract to
  maintain.

---

## Import Rules

### Import the Symbol, Not the Path

Import the specific class, function, or constant you need — do not use deep dotted namespace access in code.

| Do                                                         | Don't                                                              |
|------------------------------------------------------------|--------------------------------------------------------------------|
| `from omni.flux.job_queue.core.execute import JobExecutor` | `omni.flux.job_queue.core.execute.JobExecutor(...)` inline in code |
| `from pxr import UsdGeom`                                  | `pxr.UsdGeom.Xformable` scattered through the file                 |

Long dotted paths create hidden coupling — if the module path changes, every call site needs updating instead
of a single import line. They also hurt readability and make grep-based refactoring unreliable.

### Relative Imports Within an Extension

When importing from the same extension, use **relative imports** (`from .module import Class`) instead of
fully-qualified paths.

| Do                                                 | Don't                                                                                 |
|----------------------------------------------------|---------------------------------------------------------------------------------------|
| `from .pipeline_context import UsdPipelineContext` | `from lightspeed.trex.asset_pipeline.core.pipeline_context import UsdPipelineContext` |
| `from .display_adapter import JobDisplayAdapter`   | `from omni.flux.job_queue.widget.display_adapter import JobDisplayAdapter`            |

Relative imports make it clear the dependency is internal to the extension and survive extension renames.
Use absolute imports only for cross-extension dependencies.

---

## Smell Tests

Stop and rethink if you hit any of these:

| Smell                                                        | What it means                                                                   |
|--------------------------------------------------------------|---------------------------------------------------------------------------------|
| "It works if I add a `sleep`"                                | Broken async or data flow — something is racing                                 |
| "It works if I read from the widget instead of from storage" | State is out of sync between the UI and the backing store                       |
| "It passes alone but fails alongside other tests"            | Shared mutable state is leaking between tests                                   |
| "I need a flag to skip this code path"                       | Ask: why does that path run when it shouldn't? Fix the condition, not the path. |
| "I'll just use `getattr` with a default"                     | The type hierarchy is incomplete — add the field to a base class or protocol.   |
