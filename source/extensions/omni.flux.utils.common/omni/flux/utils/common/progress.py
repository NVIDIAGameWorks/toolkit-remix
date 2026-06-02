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

import asyncio
import concurrent.futures
import threading
from collections.abc import Callable
from typing import Any

import omni.kit.app

__all__ = [
    "INDETERMINATE_PROGRESS_TOTAL",
    "run_worker_with_latest_progress",
]

INDETERMINATE_PROGRESS_TOTAL = -1


class _LatestProgress:
    def __init__(self):
        self._lock = threading.Lock()
        self._current = 0
        self._total = INDETERMINATE_PROGRESS_TOTAL
        self._status = None
        self._changed = False

    def queue(self, current: int, total: int | None = None, status: Any | None = None):
        """Queue the latest worker progress state.

        Args:
            current: Current progress count.
            total: Optional total progress count.
            status: Optional progress status payload.
        """
        with self._lock:
            self._current = current
            if total is not None:
                self._total = total
            if status is not None:
                self._status = status
            self._changed = True

    def pop_latest(self) -> tuple[int, int, Any] | None:
        """Pop the latest queued progress state.

        Returns:
            The latest progress state, or ``None`` when no new progress was queued.
        """
        with self._lock:
            if not self._changed:
                return None
            self._changed = False
            return self._current, self._total, self._status


async def run_worker_with_latest_progress(
    worker: Callable[[Callable[[int, int | None, Any | None], None]], Any],
    progress_callback: Callable[[int, int, Any], Any] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    cancelled_result: Any = None,
    finish_worker_on_cancel: bool = False,
):
    """Run blocking work while polling only the latest queued progress once per Kit frame.

    Args:
        worker: Function to run on the worker thread. The function receives a progress queue callback.
        progress_callback: Optional callback receiving current count, total count, and status.
        is_cancelled: Optional callback returning whether cancellation was requested.
        cancelled_result: Value returned when cancellation completes without propagating an exception.
        finish_worker_on_cancel: Whether cancellation should wait for the worker to finish before returning.

    Returns:
        The worker result, or ``cancelled_result`` when cancellation is requested and completed.

    Raises:
        asyncio.CancelledError: If the caller task is cancelled.
        Exception: Any exception raised by the worker.
    """
    loop = asyncio.get_event_loop()
    app = omni.kit.app.get_app()
    progress_done = threading.Event()
    latest_progress = _LatestProgress()

    def worker_with_progress():
        try:
            return worker(latest_progress.queue)
        finally:
            progress_done.set()

    def apply_progress(progress: tuple[int, int, Any] | None):
        if progress_callback and progress:
            progress_callback(*progress)

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    worker_future = None
    shutdown_wait = True

    async def wait_for_worker_completion():
        while not progress_done.is_set():
            await app.next_update_async()
            apply_progress(latest_progress.pop_latest())
        apply_progress(latest_progress.pop_latest())

    try:
        worker_future = loop.run_in_executor(executor, worker_with_progress)

        def cancellation_requested() -> bool:
            return bool(is_cancelled and is_cancelled())

        while not progress_done.is_set():
            await app.next_update_async()
            apply_progress(latest_progress.pop_latest())
            if cancellation_requested():
                if finish_worker_on_cancel:
                    await wait_for_worker_completion()
                    await worker_future
                else:
                    worker_future.cancel()
                    shutdown_wait = False
                return cancelled_result

        apply_progress(latest_progress.pop_latest())
        return await worker_future
    except asyncio.CancelledError:
        if finish_worker_on_cancel and worker_future is not None:
            await wait_for_worker_completion()
            raise
        if worker_future is not None:
            worker_future.cancel()
        shutdown_wait = False
        raise
    finally:
        executor.shutdown(wait=shutdown_wait)
