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

from . import handlers, persistence
from .interface import QueueInterface

__all__ = ("JobQueueCore",)


class JobQueueCore:
    """Own the process-wide queue, persistence, scheduler, and Apply runtime."""

    def __init__(self, database_path: str) -> None:
        """Create and recover the complete queue runtime.

        Args:
            database_path: SQLite database used to persist queue work.

        Raises:
            Exception: If any runtime component cannot be started. Already-created components are released first.
        """
        self._queue: QueueInterface | None = None
        self._persistence_started = False
        try:
            persistence.startup()
            self._persistence_started = True
            self._queue = QueueInterface(database_path, clear_incompatible_database=True)
            self._queue.recover_interrupted_jobs()
            persistence.get_registry().set_changed_callback(self._queue.notify_schedule_conditions_changed)
            handlers.startup(self._queue)
        except Exception:
            self.destroy()
            raise

    @property
    def queue(self) -> QueueInterface:
        """Return the active queue interface.

        Returns:
            Process-wide persistent queue.

        Raises:
            RuntimeError: If this runtime has already been destroyed.
        """
        if self._queue is None:
            raise RuntimeError("Job queue core is shut down")
        return self._queue

    def destroy(self) -> None:
        """Stop the queue runtime and release persistence after asynchronous work settles."""
        queue = self._queue
        self._queue = None
        if queue is not None:
            queue.shutdown()

        shutdown_task = handlers.shutdown()
        if self._persistence_started:
            persistence.get_registry().set_changed_callback(None)
        if shutdown_task is None:
            self._shutdown_persistence()
        else:
            shutdown_task.add_done_callback(self._on_handlers_shutdown)

    def _on_handlers_shutdown(self, _task: asyncio.Task[None]) -> None:
        """Release persistence after active Apply work stops using serialization.

        Args:
            _task: Completed Apply-runtime shutdown task.
        """
        self._shutdown_persistence()

    def _shutdown_persistence(self) -> None:
        """Release the persistence registry once."""
        if self._persistence_started:
            persistence.shutdown()
            self._persistence_started = False
