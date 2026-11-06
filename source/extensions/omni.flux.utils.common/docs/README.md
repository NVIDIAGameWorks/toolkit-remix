# Flux Common Utilities

Shared utilities and wrappers around Kit functionality for use across Flux extensions.

## Responsibilities

Provide shared helpers for USD data, light classification, paths, events, and serialization.

## Non-Responsibilities

Application-specific policies and UI controls belong to their consuming extensions.

## Architecture

Helpers are organized by domain. The `lights` module provides the shared `LightTypes` enum and two classifiers:

- `get_light_type(prim)` accepts a USD prim and recognizes supported schema families, including derived and versioned lights.
- `get_light_type_from_type_name(name)` matches exact type-name strings, including `DomeLight_1`.

Both return a `LightTypes` value or `None` for unsupported types, unknown names, or invalid prims.

**5.0.0 migration:** `get_light_type()` now requires a prim. Pass it directly instead of `prim.GetTypeName()`;
string-only callers must use `get_light_type_from_type_name()`, which preserves the previous exact-name mappings.

`weak_callback(bound_method)` forwards calls without retaining the method owner and returns `None` after the owner
is released. Retain the model subscription separately for as long as notifications are needed.

## TaskTracker

`TaskTracker` runs at most one asyncio task per key, for example one submission per USD context, or one per widget
with a fixed key such as `None`.

- `start(key, coroutine_fn, name=None)` creates the task and returns it, or returns None while the key's task is
  still running. `coroutine_fn` is only called when the task starts.
- `cancel_all()` cancels every task, but each key stays taken until its task settles, so a new task can never start
  beside one that is still cancelling.
- The tracker frees a key from a done callback, which also runs for a task cancelled before it starts. A caller that
  must react once the key is free, such as re-enabling a button, adds its own done callback to the returned task:
  done callbacks run in the order they were added.

```python
from functools import partial

from omni.flux.utils.common.task_tracker import TaskTracker

_submissions = TaskTracker()

task = _submissions.start(context_name, partial(prepare_and_submit, context_name), name=f"Submit:{context_name}")
if task is not None:
    task.add_done_callback(lambda _task: refresh_run_button())
```
