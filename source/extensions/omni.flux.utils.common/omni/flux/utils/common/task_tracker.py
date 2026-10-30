"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

from __future__ import annotations

__all__ = ["TaskTracker"]

import asyncio
from collections.abc import Callable, Coroutine, Hashable
from functools import partial
from typing import Any


class TaskTracker:
    """Run at most one task per key, such as one submission per USD context.

    A key stays taken until its task settles, even after `cancel_all()`, so a new task can never replace one that is
    still cancelling. A caller that must react after the key is free adds its own done callback to the returned task:
    done callbacks run in the order they were added, after the tracker's.
    """

    def __init__(self):
        """Start with no task."""
        self._tasks: dict[Hashable, asyncio.Task[Any]] = {}

    def start(
        self, key: Hashable, coroutine_fn: Callable[[], Coroutine[Any, Any, Any]], name: str | None = None
    ) -> asyncio.Task[Any] | None:
        """Start a task for the key, unless one is still running for it.

        Args:
            key: Owner of the task, such as a USD context name.
            coroutine_fn: Creates the coroutine. It is called only when the task starts.
            name: Optional task name for debugging.

        Returns:
            The new task, or None when the key is taken.
        """
        if self.is_running(key):
            return None
        task = self._tasks[key] = asyncio.ensure_future(coroutine_fn())
        if name is not None:
            task.set_name(name)
        # A done callback also runs for a task cancelled before it starts, unlike a finally block in the coroutine.
        task.add_done_callback(partial(self._release, key))
        return task

    def is_running(self, key: Hashable) -> bool:
        """Return whether the key's task has not settled yet."""
        task = self._tasks.get(key)
        return task is not None and not task.done()

    def cancel_all(self) -> None:
        """Cancel every task. Each key stays taken until its task settles."""
        for task in self._tasks.values():
            task.cancel()

    def _release(self, key: Hashable, task: asyncio.Task[Any]) -> None:
        """Free the key unless a newer task already owns it."""
        if self._tasks.get(key) is task:
            del self._tasks[key]
