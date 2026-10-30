# omni.flux.utils.dialog

This extension provides a set of dialog windows for use in Omniverse applications.

## Cancellable progress

`ProgressPopup.run_cancellable(title, status_text, work)` shows a modal popup while an async task runs, and returns
`(result, cancelled)`. It calls `work` with two keyword arguments:

- `progress(current, total, status=None)`: updates the bar and, when given, the status text. A total of zero or less
  leaves the bar where it is. It is `ProgressPopup.report_progress()`.
- `is_cancelled()`: returns whether the user clicked Cancel. The task polls it and stops early. Cancel does not
  interrupt the task.

The popup always closes, even when `work` raises. The exception reaches the caller.

```python
from functools import partial

from omni.flux.utils.dialog.progress_popup import ProgressPopup

graphs, cancelled = await ProgressPopup.run_cancellable(
    "Preparing Jobs", "Preparing jobs...", partial(core.prepare_submission, prim_paths=paths)
)
if cancelled:
    return
```
