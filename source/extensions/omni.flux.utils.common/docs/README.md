# Overview

Assorted utilities and/or wrappers around KIT functions.

A place for functionality that is applicable for use in any other flux extension.

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
