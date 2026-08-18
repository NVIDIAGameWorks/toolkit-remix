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

import asyncio
import datetime
import pathlib
import uuid
from typing import Any

import carb
from omni.flux.utils.common import EventSubscription

from .errors import JobError, JobExecutionError
from .interface import QueueInterface
from .job import JobOutputs, JobProgress

__all__ = ("JobExecutor", "JobScheduler")


def _initialize_job_logs(stdout_path: pathlib.Path, stderr_path: pathlib.Path) -> None:
    """Create empty per-job log files before execution starts.

    Args:
        stdout_path: Lifecycle log path.
        stderr_path: Failure log path.
    """
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")


def _append_job_log(path: pathlib.Path, message: str) -> None:
    """Append one timestamped entry to a per-job log.

    Args:
        path: Queue-owned log file.
        message: Text to append.
    """
    timestamp = datetime.datetime.now().isoformat(timespec="microseconds")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"[{timestamp}] {message}\n")


async def _write_job_log(path: pathlib.Path, message: str) -> None:
    """Write a job log without blocking execution or failing the job on log I/O.

    Args:
        path: Queue-owned log file.
        message: Text to append.
    """
    try:
        await asyncio.to_thread(_append_job_log, path, message)
    except OSError as error:
        carb.log_warn(f"Could not write job log {path}: {error}")


async def _finish_despite_cancellation(task: asyncio.Task[Any]) -> Any:
    """Wait for required cleanup despite repeated cancellation.

    Args:
        task: Required owned work that must reach a result.

    Returns:
        Completed task result.
    """
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    return task.result()


async def _persist_failure(
    interface: QueueInterface,
    job_id: uuid.UUID,
    failure: JobError,
    reason: str,
    stderr_path: pathlib.Path,
) -> None:
    """Persist one terminal failure and its diagnostic despite cancellation.

    Args:
        interface: Queue that owns the terminal transition.
        job_id: Active job identifier.
        failure: Retained technical diagnostic.
        reason: User-facing failure reason.
        stderr_path: Queue-owned diagnostic log path.

    Raises:
        asyncio.CancelledError: After required persistence and logging settle.
    """
    cancellation_received = False
    persist_task = asyncio.create_task(asyncio.to_thread(interface.fail_job, job_id, failure, reason))
    try:
        changed = await asyncio.shield(persist_task)
    except asyncio.CancelledError:
        cancellation_received = True
        changed = await _finish_despite_cancellation(persist_task)
    if changed:
        log_task = asyncio.create_task(_write_job_log(stderr_path, _format_failure_log(reason, failure)))
        try:
            await asyncio.shield(log_task)
        except asyncio.CancelledError:
            cancellation_received = True
            await _finish_despite_cancellation(log_task)
    if cancellation_received:
        raise asyncio.CancelledError


def _format_failure_log(reason: str, error: JobError) -> str:
    """Format safe context and retained diagnostics for the details log.

    Args:
        reason: User-facing failure reason.
        error: Retained technical diagnostic.

    Returns:
        Multiline per-job failure entry.
    """
    details = f"{error.exception_type}: {error.message}"
    return f"{reason}\n{details}\n{error.traceback}" if error.traceback else f"{reason}\n{details}"


class JobExecutor:
    """Execute typed jobs and persist progress, outputs, or failure."""

    def __init__(self, interface: QueueInterface) -> None:
        """Retain the queue that owns execution state.

        Args:
            interface: Persistent typed job queue.
        """
        self.interface = interface

    async def execute(self, job_id: uuid.UUID) -> None:
        """Run one conditionally scheduled job through a terminal transition.

        Args:
            job_id: Scheduled job identifier.

        Raises:
            asyncio.CancelledError: If execution cancellation is persisted and propagated.
        """
        job_directory = self.interface.get_job_directory(job_id)
        stdout_path = job_directory / "logs" / "stdout.log"
        stderr_path = job_directory / "logs" / "stderr.log"
        start_task = asyncio.create_task(asyncio.to_thread(self.interface.start_job, job_id))
        completion_persisted = False
        try:
            if not await asyncio.shield(start_task):
                return
            await asyncio.to_thread(_initialize_job_logs, stdout_path, stderr_path)
            job = await asyncio.to_thread(self.interface.get_job, job_id)
            await _write_job_log(stdout_path, f"Starting {job.name}")
            inputs = await asyncio.to_thread(self.interface.resolve_job_inputs, job_id)

            async def update_progress(progress: JobProgress) -> None:
                """Persist one structured progress update without blocking the event loop.

                Args:
                    progress: Current structured progress.

                Raises:
                    RuntimeError: If the job is no longer active.
                """
                accepted = await asyncio.to_thread(self.interface.update_progress, job_id, progress)
                if not accepted:
                    raise RuntimeError(f"Job {job_id} is no longer active")

            outputs = await job.execute(job_directory, inputs, update_progress)
            if not isinstance(outputs, JobOutputs):
                raise TypeError(f"{type(job).__name__}.execute must return JobOutputs")
            await _write_job_log(stdout_path, "Completed successfully")
            completion_task = asyncio.create_task(asyncio.to_thread(self.interface.complete_job, job_id, outputs))
            try:
                completed = await asyncio.shield(completion_task)
            except asyncio.CancelledError:
                completed = await _finish_despite_cancellation(completion_task)
                completion_persisted = completed
                raise
            if not completed:
                raise RuntimeError(f"Job {job_id} lost its completion transition")
            completion_persisted = True
        except asyncio.CancelledError:
            if completion_persisted:
                raise
            failure = JobError("CancelledError", "Job execution was cancelled", "")
            reason = "The job was cancelled before completion."
            try:
                try:
                    should_settle = await _finish_despite_cancellation(start_task)
                except Exception as error:  # noqa: BLE001 - failed start leaves queue ownership ambiguous.
                    should_settle = True
                    carb.log_error(f"Could not finish starting cancelled job {job_id}: {error}")
                if should_settle:
                    settle_task = asyncio.create_task(
                        _persist_failure(self.interface, job_id, failure, reason, stderr_path)
                    )
                    await _finish_despite_cancellation(settle_task)
            except Exception as error:  # noqa: BLE001 - cancellation still must propagate after failed cleanup.
                carb.log_error(f"Could not settle cancelled job {job_id}: {error}")
            raise
        except JobExecutionError as failure:
            diagnostic = JobError.from_exception(failure.diagnostic)
            await _persist_failure(self.interface, job_id, diagnostic, failure.reason, stderr_path)
        except Exception as error:  # noqa: BLE001 - Product-owned Job.execute failures need durable queue state.
            diagnostic = JobError.from_exception(error)
            reason = "The job could not be completed."
            await _persist_failure(self.interface, job_id, diagnostic, reason, stderr_path)


class JobScheduler:
    """Dispatch jobs from committed events with exact job-type concurrency."""

    def __init__(self, interface: QueueInterface) -> None:
        """Create an idle core-owned scheduler.

        Args:
            interface: Persistent queue to schedule.
        """
        self.interface = interface
        self.executor = JobExecutor(interface)
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._failure: BaseException | None = None
        self._active: set[asyncio.Task[None]] = set()
        self._mutation_subscription: EventSubscription | None = None
        self._conditions_subscription: EventSubscription | None = None

    def start(self) -> None:
        """Start event-driven dispatch if it is not already running.

        Raises:
            RuntimeError: If no event loop is running in the current thread.
        """
        if self._task is not None:
            if not self._running:
                raise RuntimeError("The scheduler cannot start while its previous generation is stopping")
            return
        if self._failure is not None:
            raise RuntimeError(
                "The previous scheduler generation failed; call stop() to observe the failure"
            ) from self._failure
        self._loop = asyncio.get_running_loop()
        self._running = True
        mutation_subscription = self.interface.subscribe_mutation(self._on_queue_event)
        try:
            conditions_subscription = self.interface.subscribe_schedule_conditions_changed(self._on_queue_event)
            task = self._loop.create_task(self._run())
        except Exception:
            mutation_subscription = None
            self._running = False
            self._loop = None
            raise
        self._mutation_subscription = mutation_subscription
        self._conditions_subscription = conditions_subscription
        self._task = task
        task.add_done_callback(self._on_run_finished)
        self._wake.set()

    async def stop(self) -> None:
        """Pause new dispatch and wait for active jobs to finish."""
        task = self._task
        if task is None:
            failure = self._failure
            self._failure = None
            if failure is not None:
                raise failure
            return
        self._running = False
        self._mutation_subscription = None
        self._conditions_subscription = None
        self._wake.set()
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await _finish_despite_cancellation(task)
            raise
        except BaseException:
            self._failure = None
            raise

    def is_running(self) -> bool:
        """Return whether new job dispatch is enabled.

        Returns:
            Whether the scheduler accepts dispatch work.
        """
        return self._running

    async def _run(self) -> None:
        """Dispatch runnable jobs when queue or product readiness changes."""
        pending_claims: set[uuid.UUID] = set()
        try:
            while self._running:
                self._wake.clear()
                claim_task = asyncio.create_task(asyncio.to_thread(self.interface.claim_runnable_jobs))
                try:
                    claimed = await asyncio.shield(claim_task)
                except asyncio.CancelledError:
                    pending_claims.update(await _finish_despite_cancellation(claim_task))
                    raise
                pending_claims.update(claimed)
                if not self._running:
                    break
                for job_id in claimed:
                    if not self._running:
                        break
                    execution = self.executor.execute(job_id)
                    try:
                        task = asyncio.create_task(execution)
                    except Exception:
                        execution.close()
                        raise
                    self._active.add(task)
                    task.add_done_callback(self._on_job_finished)
                    pending_claims.remove(job_id)
                if not claimed:
                    await self._wake.wait()
        finally:
            self._running = False
            self._mutation_subscription = None
            self._conditions_subscription = None
            try:
                if pending_claims:
                    release_task = asyncio.create_task(
                        asyncio.to_thread(self.interface.release_scheduled_jobs, tuple(pending_claims))
                    )
                    await _finish_despite_cancellation(release_task)
            finally:
                if self._active:
                    await asyncio.gather(*tuple(self._active), return_exceptions=True)
                self._loop = None

    def _on_run_finished(self, task: asyncio.Task[None]) -> None:
        """Release scheduler ownership after one generation fully exits."""
        if self._task is task:
            self._task = None
        if not task.cancelled() and (error := task.exception()) is not None:
            self._failure = error
            carb.log_error(f"Job scheduler failed: {error}")

    def _on_queue_event(self, *_args) -> None:
        """Wake dispatch safely from any process-local event callback.

        Args:
            *_args: Event payload ignored by the scheduler.
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._wake.set)
        except RuntimeError as error:
            carb.log_error(f"Could not wake the job scheduler: {error}")

    def _on_job_finished(self, task: asyncio.Task[None]) -> None:
        """Release exact-type capacity and consume task failure.

        Args:
            task: Completed owned execution task.
        """
        self._active.discard(task)
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                carb.log_error(f"Job executor failed: {error}")
        self._wake.set()
