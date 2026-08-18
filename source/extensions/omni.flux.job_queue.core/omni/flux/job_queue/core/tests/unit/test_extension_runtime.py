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
import types
import uuid
from unittest import mock

import omni.kit.app
import omni.kit.test
from omni.flux.job_queue.core import handlers
from omni.flux.job_queue.core import core as queue_core


class _SchedulerProbe:
    """Expose deterministic stop/start ordering for settings reconciliation."""

    def __init__(self):
        """Create a running scheduler with a blocked stop."""
        self.running = True
        self.stop_started = asyncio.Event()
        self.allow_stop = asyncio.Event()
        self.start_calls = 0

    def start(self) -> None:
        """Record a synchronous scheduler start."""
        self.running = True
        self.start_calls += 1

    async def stop(self) -> None:
        """Wait until the test permits the in-flight stop to finish."""
        self.stop_started.set()
        await self.allow_stop.wait()
        self.running = False


class TestExtensionRuntime(omni.kit.test.AsyncTestCase):
    """Validate startup rollback across queue and handler initialization failures."""

    @staticmethod
    async def _wait_for_scheduler_state(scheduler, expected: bool) -> None:
        """Wait for main-loop settings reconciliation to reach one state.

        Args:
            scheduler: Core scheduler whose running state is observed.
            expected: Expected running state.

        Raises:
            AssertionError: If reconciliation does not settle promptly.
        """
        for _ in range(100):
            reconcile_task = handlers._scheduler_reconcile_task
            if scheduler.is_running() is expected and (reconcile_task is None or reconcile_task.done()):
                return
            await omni.kit.app.get_app().next_update_async()
        raise AssertionError(f"Scheduler did not reach running={expected}")

    @staticmethod
    def _startup_with_failure(failure_stage: str):
        """Run startup with one injected failure and return owned mocks."""
        registry = mock.Mock()
        queue = mock.Mock()
        if failure_stage == "recovery":
            queue.recover_interrupted_jobs.side_effect = RuntimeError("recovery failed")
        handler_startup = mock.Mock(
            side_effect=RuntimeError("handlers failed") if failure_stage == "handlers" else None
        )
        with (
            mock.patch.object(queue_core.persistence, "startup"),
            mock.patch.object(queue_core.persistence, "get_registry", return_value=registry),
            mock.patch.object(queue_core.persistence, "shutdown") as persistence_shutdown,
            mock.patch.object(queue_core, "QueueInterface", return_value=queue),
            mock.patch.object(queue_core.handlers, "startup", handler_startup),
            mock.patch.object(queue_core.handlers, "shutdown", return_value=None) as handler_shutdown,
        ):
            try:
                queue_core.JobQueueCore("queue.sqlite")
            except RuntimeError as error:
                captured = error
            else:
                raise AssertionError("Startup unexpectedly succeeded")
        return captured, queue, registry, handler_startup, handler_shutdown, persistence_shutdown

    async def test_recovery_failure_rolls_back_persistence_and_queue(self):
        """Database recovery failure leaves no partial process-owned runtime."""
        # Arrange
        failure_stage = "recovery"

        # Act
        result = self._startup_with_failure(failure_stage)

        # Assert
        error, queue, registry, handler_startup, handler_shutdown, persistence_shutdown = result
        self.assertEqual(str(error), "recovery failed")
        queue.shutdown.assert_called_once_with()
        registry.set_changed_callback.assert_called_once_with(None)
        handler_startup.assert_not_called()
        handler_shutdown.assert_called_once_with()
        persistence_shutdown.assert_called_once_with()

    async def test_handler_startup_failure_rolls_back_persistence_and_queue(self):
        """Handler startup failure removes the recovered queue and persistence registry."""
        # Arrange
        failure_stage = "handlers"

        # Act
        result = self._startup_with_failure(failure_stage)

        # Assert
        error, queue, registry, handler_startup, handler_shutdown, persistence_shutdown = result
        self.assertEqual(str(error), "handlers failed")
        queue.shutdown.assert_called_once_with()
        registry.set_changed_callback.assert_any_call(None)
        handler_startup.assert_called_once()
        handler_shutdown.assert_called_once_with()
        persistence_shutdown.assert_called_once_with()

    async def test_scheduler_setting_reconcile_honors_true_arriving_during_stop(self):
        """A false-to-true race cannot leave the core scheduler disabled."""
        # Arrange
        scheduler = _SchedulerProbe()
        settings = types.SimpleNamespace(scheduler_enabled=False)

        async def toggle_during_stop() -> None:
            """Enable scheduling while one asynchronous stop is in flight."""
            task = asyncio.create_task(handlers._reconcile_scheduler_setting())
            await asyncio.wait_for(scheduler.stop_started.wait(), 2)
            settings.scheduler_enabled = True
            scheduler.allow_stop.set()
            await asyncio.wait_for(task, 2)

        with (
            mock.patch.object(handlers, "_scheduler", scheduler),
            mock.patch.object(handlers, "_settings", settings),
        ):
            # Act
            await toggle_during_stop()

        # Assert
        self.assertTrue(scheduler.running)
        self.assertEqual(scheduler.start_calls, 1)

    async def test_scheduler_setting_change_without_running_loop_is_marshaled(self):
        """A real settings callback outside asyncio reaches the owning Kit loop."""
        # Arrange
        settings = handlers._settings
        scheduler = handlers._scheduler
        self.assertIsNotNone(settings)
        self.assertIsNotNone(scheduler)
        original = settings.scheduler_enabled
        expected = not original

        try:
            # Act
            await asyncio.to_thread(settings.set_scheduler_enabled, expected)
            await self._wait_for_scheduler_state(scheduler, expected)

            # Assert
            self.assertEqual(scheduler.is_running(), expected)
        finally:
            settings.set_scheduler_enabled(original)
            await self._wait_for_scheduler_state(scheduler, original)

    async def test_auto_apply_setting_reconciles_only_on_false_to_true_edge(self):
        """Repeated writes do not enqueue duplicate automatic Apply scans."""
        # Arrange
        job_id = uuid.uuid4()
        queue = mock.Mock()
        queue.iter_snapshot.return_value = iter([types.SimpleNamespace(job_id=job_id)])
        executor = mock.Mock()
        settings = types.SimpleNamespace(auto_apply=False)

        def write_sequence() -> None:
            """Write false, true, and repeated true auto-Apply settings."""
            handlers._on_auto_apply_changed(None, mock.Mock())
            settings.auto_apply = True
            handlers._on_auto_apply_changed(None, mock.Mock())
            handlers._on_auto_apply_changed(None, mock.Mock())

        with (
            mock.patch.object(handlers, "_queue", queue),
            mock.patch.object(handlers, "_apply_executor", executor),
            mock.patch.object(handlers, "_settings", settings),
            mock.patch.object(handlers, "_last_auto_apply", False),
        ):
            # Act
            write_sequence()

        # Assert
        executor.request_reconcile.assert_called_once_with(job_id)
