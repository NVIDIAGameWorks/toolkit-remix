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
import contextlib
import dataclasses
import pathlib
import threading
import uuid
from collections.abc import Callable
from typing import ClassVar
from unittest import mock

import omni.kit.test
import omni.flux.job_queue.core.persistence as persistence
from omni.flux.job_queue.core import handlers
from omni.flux.job_queue.core.apply_executor import ApplyExecutor
from omni.flux.job_queue.core.apply_handler_base import ApplyHandler
from omni.flux.job_queue.core.apply_handler_registry import ApplyHandlerRegistry
from omni.flux.job_queue.core.enums import ApplyDisposition, ApplyOperation, ApplyPolicy
from omni.flux.job_queue.core.errors import ApplyExecutionError, QueueSubmissionError
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.models import QueueJobSnapshot
from omni.flux.job_queue.core.job import (
    ApplyBinding,
    Job,
    JobInputs,
    JobOutputPort,
    JobOutputs,
    JobProgressCallback,
)
from omni.flux.job_queue.core.persistence import PersistenceCodec
from omni.flux.job_queue.core.serializer import serialize

from .helpers import temp_db_path


@dataclasses.dataclass(frozen=True)
class _Target:
    """Represent one exact persisted Apply target."""

    name: str


@dataclasses.dataclass(frozen=True)
class _Receipt:
    """Preserve the value observed before the first Apply."""

    original: int
    applied: int


VALUE = JobOutputPort("value", int)


class _ApplyHandler(ApplyHandler[int, _Target, _Receipt]):
    """Record typed Apply and Revert calls for lifecycle assertions."""

    name = "test.ApplyHandler"
    input_type = int
    target_type = _Target
    receipt_type = _Receipt
    apply_policy = ApplyPolicy.ALWAYS_MANUAL
    calls: ClassVar[list[tuple[str, _Receipt]]] = []
    captures: ClassVar[list[_Receipt]] = []
    fail: ClassVar[bool] = False
    fail_after_mutation: ClassVar[bool] = False
    fail_revert: ClassVar[bool] = False
    cancel: ClassVar[bool] = False
    domain_failure: ClassVar[bool] = False
    applied: ClassVar[asyncio.Event | None] = None
    release: ClassVar[asyncio.Event | None] = None
    active: ClassVar[int] = 0
    peak: ClassVar[int] = 0
    target_values: ClassVar[dict[str, int]] = {}
    before_mutation: ClassVar[Callable[[_Receipt], None] | None] = None
    block_reason: ClassVar[str | None] = None

    def get_apply_block_reason(self, target: _Target, operation: ApplyOperation) -> str | None:
        """Return the configured environmental prerequisite failure.

        Args:
            target: Exact persisted Apply target, unused by this controlled handler.
            operation: Exact operation being considered, unused by this controlled handler.

        Returns:
            Configured user-facing reason, or ``None`` when Apply can run.
        """
        del target, operation
        return self.block_reason

    async def capture_receipt(self, value: int, target: _Target) -> _Receipt:
        """Capture the durable original value without mutating the target.

        Args:
            value: Exact job output value.
            target: Exact persisted Apply target.

        Returns:
            Durable receipt for idempotent Apply and Revert.
        """
        receipt = _Receipt(original=self.target_values[target.name], applied=value)
        self.captures.append(receipt)
        return receipt

    async def apply(self, value: int, target: _Target, receipt: _Receipt) -> None:
        """Idempotently apply the output using the durable pre-mutation receipt.

        Args:
            value: Exact job output value.
            target: Exact persisted Apply target.
            receipt: Durable receipt captured before the first mutation.

        Raises:
            ValueError: If configured to fail.
        """
        type(self).active += 1
        type(self).peak = max(type(self).peak, type(self).active)
        try:
            self.calls.append(("apply", receipt))
            if self.applied is not None:
                self.applied.set()
            if self.release is not None:
                await self.release.wait()
            if self.fail:
                raise ValueError("apply failed")
            if self.cancel:
                raise asyncio.CancelledError("apply cancelled")
            if self.domain_failure:
                raise ApplyExecutionError("The selected project cannot accept this output.", ValueError("secret"))
            if type(self).before_mutation is not None:
                type(self).before_mutation(receipt)
            self.target_values[target.name] = value
            if self.fail_after_mutation:
                raise ValueError("apply failed after mutation")
        finally:
            type(self).active -= 1

    async def revert(self, value: int, target: _Target, receipt: _Receipt) -> None:
        """Record one exact typed Revert operation.

        Args:
            value: Exact job output value.
            target: Exact persisted Apply target.
            receipt: Durable receipt captured before the first Apply attempt.
        """
        del value
        self.calls.append(("revert", receipt))
        if self.fail_revert:
            raise ValueError("revert failed")
        self.target_values[target.name] = receipt.original


@dataclasses.dataclass
class _ApplyJob(Job):
    """Produce one integer output bound to the typed handler."""

    value: int = 1
    output_ports = (VALUE,)

    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Return the configured exact typed output.

        Args:
            job_directory: Queue-owned job directory.
            inputs: Empty typed input mapping.
            progress_callback: Unused progress callback.

        Returns:
            Configured exact typed output.
        """
        del job_directory, inputs, progress_callback
        return JobOutputs({VALUE: self.value})


_APPLY_HANDLER_CODEC = PersistenceCodec("test.ApplyHandler", _ApplyHandler)
_MISMATCHED_APPLY_HANDLER_CODEC = PersistenceCodec("test.MismatchedApplyHandler", _ApplyHandler)
_APPLY_JOB_CODEC = PersistenceCodec(
    "test.ApplyJob",
    _ApplyJob,
    lambda value: (value.job_id, value.name, value.skip_reason, value.apply_binding, value.value),
    lambda value: _ApplyJob(*value),
)


class _PausedSnapshotQueue(QueueInterface):
    """Pause one completed snapshot read to expose a concurrent durable change."""

    def __init__(self, db_path: pathlib.Path):
        """Create a real SQLite queue with one controllable snapshot read.

        Args:
            db_path: Queue database path.
        """
        super().__init__(db_path)
        self.pause_job_id: uuid.UUID | None = None
        self.snapshot_read = threading.Event()
        self.resume_snapshot = threading.Event()

    def get_job_snapshot(self, job_id: uuid.UUID) -> QueueJobSnapshot:
        """Return the real snapshot after optionally pausing its first read.

        Args:
            job_id: Job identifier.

        Returns:
            Durable snapshot read before the pause.

        Raises:
            RuntimeError: If the test never releases the paused read.
        """
        snapshot = super().get_job_snapshot(job_id)
        if job_id == self.pause_job_id:
            self.pause_job_id = None
            self.snapshot_read.set()
            if not self.resume_snapshot.wait(2):
                raise RuntimeError("Timed out waiting to resume the snapshot read")
        return snapshot


_fail_receipt_encoding = False


def _encode_receipt(value: _Receipt) -> tuple[int, int]:
    """Encode one receipt unless the test requests a persistence failure."""
    if _fail_receipt_encoding:
        raise ValueError("receipt serialization failed")
    return value.original, value.applied


_RECEIPT_CODEC = PersistenceCodec("test.Receipt", _Receipt, _encode_receipt, lambda value: _Receipt(*value))
_TARGET_CODEC = PersistenceCodec(
    "test.Target",
    _Target,
    lambda value: (value.name,),
    lambda value: _Target(*value),
)
_APPLY_CODECS = (_APPLY_HANDLER_CODEC, _APPLY_JOB_CODEC, _RECEIPT_CODEC, _TARGET_CODEC)


class TestApplyRuntime(omni.kit.test.AsyncTestCase):
    """Validate typed durable Apply, Reapply, Decline, and Revert semantics."""

    async def setUp(self):
        """Reset handler probes before each test."""
        persistence.get_registry().register_codecs(_APPLY_CODECS)
        _ApplyHandler.calls = []
        _ApplyHandler.captures = []
        _ApplyHandler.fail = False
        _ApplyHandler.fail_after_mutation = False
        _ApplyHandler.fail_revert = False
        _ApplyHandler.cancel = False
        _ApplyHandler.domain_failure = False
        _ApplyHandler.applied = asyncio.Event()
        _ApplyHandler.release = None
        _ApplyHandler.active = 0
        _ApplyHandler.peak = 0
        _ApplyHandler.target_values = {"asset": 100}
        _ApplyHandler.before_mutation = None
        _ApplyHandler.block_reason = None
        _ApplyHandler.apply_policy = ApplyPolicy.ALWAYS_MANUAL
        global _fail_receipt_encoding
        _fail_receipt_encoding = False
        self.executor: ApplyExecutor | None = None
        self.registry: ApplyHandlerRegistry | None = None
        self._temp_db_contexts = []

    async def tearDown(self):
        """Stop Apply work and unregister exact persistence codecs."""
        if _ApplyHandler.release is not None:
            _ApplyHandler.release.set()
        if self.executor is not None:
            await self.executor.shutdown()
        if self.registry is not None:
            self.registry.destroy()
        persistence.get_registry().unregister_codecs(_APPLY_CODECS)
        for context in reversed(self._temp_db_contexts):
            await context.__aexit__(None, None, None)

    @contextlib.asynccontextmanager
    async def _temp_db_path(self):
        """Yield a database path whose cleanup follows runtime teardown.

        Yields:
            Temporary SQLite database path.
        """
        context = temp_db_path()
        db_path = await context.__aenter__()
        self._temp_db_contexts.append(context)
        yield db_path

    @staticmethod
    def _complete(interface: QueueInterface, value: int = 1) -> _ApplyJob:
        """Persist one completed Apply-ready job.

        Args:
            interface: Isolated queue.
            value: Output value to persist.

        Returns:
            Completed job.
        """
        job = _ApplyJob(
            value=value,
            apply_binding=ApplyBinding(output_port=VALUE, handler_type=_ApplyHandler, target=_Target("asset")),
        )
        interface.submit(job)
        interface.claim_runnable_jobs()
        interface.start_job(job.job_id)
        interface.complete_job(job.job_id, JobOutputs({VALUE: value}))
        return job

    async def _fail_and_reconcile(self, executor: ApplyExecutor, job_id: uuid.UUID) -> Exception:
        """Capture one explicit failure and reconcile once.

        Args:
            executor: Apply runtime under test.
            job_id: Completed job identifier.

        Returns:
            Failure returned to the explicit caller.
        """
        with self.assertRaises(ValueError) as raised:
            await executor.apply(job_id)
        await executor.reconcile(job_id)
        return raised.exception

    @staticmethod
    async def _decline_and_reconcile(executor: ApplyExecutor, job_id: uuid.UUID) -> None:
        """Decline and reconcile one completed job.

        Args:
            executor: Apply runtime under test.
            job_id: Completed job identifier.
        """
        await executor.decline(job_id)
        await executor.reconcile(job_id)

    @staticmethod
    async def _complete_from_worker_and_wait(
        executor: ApplyExecutor, interface: QueueInterface, job_id: uuid.UUID, value: int
    ) -> None:
        """Complete from a worker thread and await automatic main-loop Apply.

        Args:
            executor: Apply runtime under test.
            interface: Queue receiving worker-thread completion.
            job_id: In-progress job identifier.
            value: Exact output value.
        """
        await asyncio.to_thread(interface.complete_job, job_id, JobOutputs({VALUE: value}))
        await asyncio.wait_for(_ApplyHandler.applied.wait(), 2)
        await executor.wait_idle()

    @staticmethod
    def _shutdown_handlers_without_running_loop() -> tuple[object, mock.AsyncMock, mock.AsyncMock, mock.Mock]:
        """Shut down a mocked runtime on its stopped owning loop.

        Returns:
            Shutdown result, scheduler stop, executor shutdown, and registry probes.
        """
        loop = asyncio.new_event_loop()
        scheduler_stop = mock.AsyncMock()
        executor_shutdown = mock.AsyncMock()
        registry = mock.Mock()
        with (
            mock.patch.object(handlers, "_main_loop", loop),
            mock.patch.object(handlers, "_queue", mock.Mock()),
            mock.patch.object(handlers, "_registry", registry),
            mock.patch.object(handlers, "_scheduler", mock.Mock(stop=scheduler_stop)),
            mock.patch.object(handlers, "_apply_executor", mock.Mock(shutdown=executor_shutdown)),
            mock.patch.object(handlers, "_settings", mock.Mock()),
            mock.patch.object(handlers, "_background_tasks", set()),
            mock.patch.object(handlers, "_auto_apply_subscription", mock.Mock()),
            mock.patch.object(handlers, "_scheduler_subscription", mock.Mock()),
            mock.patch.object(handlers, "_scheduler_reconcile_task", None),
        ):
            try:
                result = handlers.shutdown()
            finally:
                loop.close()
        return result, scheduler_stop, executor_shutdown, registry

    @staticmethod
    def _create_executor_without_running_loop() -> bool:
        """Create an executor while its current owning loop is between ticks.

        Returns:
            Whether the executor captured the current stopped loop.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            executor = ApplyExecutor(mock.Mock(), ApplyHandlerRegistry())
            return executor._loop is loop
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    @staticmethod
    async def _register_and_wait(executor: ApplyExecutor, plugins: list[type[_ApplyHandler]]) -> None:
        """Register handlers and await automatic reconciliation.

        Args:
            executor: Apply runtime retaining the reconciliation worker.
            plugins: Exact handlers to register.
        """
        handlers.register_plugins(plugins)
        await asyncio.wait_for(_ApplyHandler.applied.wait(), 2)
        await executor.wait_idle()

    async def _decline_then_fail_apply(self, executor: ApplyExecutor, job_id: uuid.UUID) -> Exception:
        """Decline one output and fail its explicit retry.

        Args:
            executor: Apply runtime under test.
            job_id: Completed job identifier.

        Returns:
            Failure returned to the explicit caller.
        """
        await executor.decline(job_id)
        _ApplyHandler.fail = True
        with self.assertRaises(ValueError) as raised:
            await executor.apply(job_id)
        return raised.exception

    async def _recover_reapply_after_failed_revert(self, executor: ApplyExecutor, job_id: uuid.UUID) -> Exception:
        """Fail Revert, then prove Reapply remains available from the durable receipt.

        Args:
            executor: Apply runtime under test.
            job_id: Applied job identifier.

        Returns:
            Failure returned by Revert.
        """
        await executor.apply(job_id)
        _ApplyHandler.fail_revert = True
        with self.assertRaises(ValueError) as raised:
            await executor.revert(job_id)
        _ApplyHandler.fail_revert = False
        await executor.apply(job_id)
        return raised.exception

    @staticmethod
    async def _apply_two_jobs(executor: ApplyExecutor, first_id: uuid.UUID, second_id: uuid.UUID) -> tuple[int, int]:
        """Queue two Apply operations and return FIFO/overlap evidence.

        Args:
            executor: Apply runtime under test.
            first_id: First completed job identifier.
            second_id: Second completed job identifier.

        Returns:
            Handler count before release and peak overlap.
        """
        first = asyncio.create_task(executor.apply(first_id))
        second = asyncio.create_task(executor.apply(second_id))
        await asyncio.wait_for(_ApplyHandler.applied.wait(), 2)
        calls_before_release = len(_ApplyHandler.calls)
        _ApplyHandler.release.set()
        await asyncio.gather(first, second)
        return calls_before_release, _ApplyHandler.peak

    @staticmethod
    async def _apply_one_job_from_two_callers(executor: ApplyExecutor, job_id: uuid.UUID) -> None:
        """Submit one blocked job from two callers.

        Args:
            executor: Apply runtime under test.
            job_id: Completed job identifier.
        """
        first = asyncio.create_task(executor.apply(job_id))
        second = asyncio.create_task(executor.apply(job_id))
        await asyncio.wait_for(_ApplyHandler.applied.wait(), 2)
        await asyncio.sleep(0)
        _ApplyHandler.release.set()
        await asyncio.gather(first, second)

    @staticmethod
    async def _cancel_one_of_two_apply_callers(executor: ApplyExecutor, job_id: uuid.UUID) -> None:
        """Cancel one waiter without releasing its active exact-job operation.

        Args:
            executor: Apply runtime under test.
            job_id: Completed job identifier.
        """
        cancelled = asyncio.create_task(executor.apply(job_id))
        await asyncio.wait_for(_ApplyHandler.applied.wait(), 2)
        cancelled.cancel()
        await asyncio.gather(cancelled, return_exceptions=True)
        remaining = asyncio.create_task(executor.apply(job_id))
        await asyncio.sleep(0)
        _ApplyHandler.release.set()
        await remaining

    @staticmethod
    async def _conflict_with_active_apply(executor: ApplyExecutor, job_id: uuid.UUID) -> tuple[bool, BaseException]:
        """Submit Revert while Apply is blocked and return its immediate outcome.

        Args:
            executor: Apply runtime under test.
            job_id: Completed job identifier.

        Returns:
            Whether Revert settled immediately and its result.
        """
        applying = asyncio.create_task(executor.apply(job_id))
        await asyncio.wait_for(_ApplyHandler.applied.wait(), 2)
        reverting = asyncio.create_task(executor.revert(job_id))
        await asyncio.sleep(0)
        completed_immediately = reverting.done()
        _ApplyHandler.release.set()
        results = await asyncio.gather(applying, reverting, return_exceptions=True)
        return completed_immediately, results[1]

    @staticmethod
    async def _decline_queued_apply_behind_blocked_job(
        executor: ApplyExecutor, active_id: uuid.UUID, queued_id: uuid.UUID
    ) -> BaseException:
        """Decline one reserved queued Apply while an earlier job owns the lane.

        Args:
            executor: Apply runtime under test.
            active_id: Job blocking the FIFO worker.
            queued_id: Reserved job to decline.

        Returns:
            Result returned to the cancelled Apply caller.
        """
        active = asyncio.create_task(executor.apply(active_id))
        await asyncio.wait_for(_ApplyHandler.applied.wait(), 2)
        queued = asyncio.create_task(executor.apply(queued_id))
        await asyncio.sleep(0)
        declined = asyncio.create_task(executor.decline(queued_id))
        await asyncio.sleep(0)
        _ApplyHandler.release.set()
        await active
        await declined
        return (await asyncio.gather(queued, return_exceptions=True))[0]

    @staticmethod
    async def _coordinate_blocked_apply_requests(
        executor: ApplyExecutor,
        active_id: uuid.UUID,
        queued_id: uuid.UUID,
        reconcile_first: bool,
    ) -> list[BaseException | None]:
        """Run explicit Apply and reconciliation in either order behind blocked lane work.

        Args:
            executor: Apply runtime under test.
            active_id: Job blocking the FIFO worker.
            queued_id: Job requested through both Apply entry points.
            reconcile_first: Whether reconciliation enters the queue before explicit Apply.

        Returns:
            Results from the active and two coordinated callers.
        """
        active = asyncio.create_task(executor.apply(active_id))
        await asyncio.wait_for(_ApplyHandler.applied.wait(), 2)
        first_call = executor.reconcile if reconcile_first else executor.apply
        second_call = executor.apply if reconcile_first else executor.reconcile
        first = asyncio.create_task(first_call(queued_id))
        await asyncio.sleep(0)
        second = asyncio.create_task(second_call(queued_id))
        await asyncio.sleep(0)
        _ApplyHandler.release.set()
        results = await asyncio.gather(active, first, second, return_exceptions=True)
        await executor.wait_idle()
        return results

    @staticmethod
    async def _join_active_reconciliation(executor: ApplyExecutor, job_id: uuid.UUID) -> list[BaseException | None]:
        """Join explicit Apply to active reconciliation while coalescing repeated notifications.

        Args:
            executor: Apply runtime under test.
            job_id: Completed job identifier.

        Returns:
            Results from reconciliation and explicit Apply.
        """
        reconciling = asyncio.create_task(executor.reconcile(job_id))
        await asyncio.wait_for(_ApplyHandler.applied.wait(), 2)
        applying = asyncio.create_task(executor.apply(job_id))
        for _ in range(3):
            executor.request_reconcile(job_id)
        await asyncio.sleep(0)
        _ApplyHandler.release.set()
        results = await asyncio.gather(reconciling, applying, return_exceptions=True)
        await executor.wait_idle()
        return results

    @staticmethod
    async def _decline_coordinated_queued_apply(
        executor: ApplyExecutor,
        active_id: uuid.UUID,
        queued_id: uuid.UUID,
    ) -> list[BaseException | None]:
        """Decline reconciliation and explicit Apply coordinated behind blocked lane work.

        Args:
            executor: Apply runtime under test.
            active_id: Job blocking the FIFO worker.
            queued_id: Job requested by reconciliation and explicit Apply.

        Returns:
            Results from the active and two coordinated callers.
        """
        active = asyncio.create_task(executor.apply(active_id))
        await asyncio.wait_for(_ApplyHandler.applied.wait(), 2)
        reconciling = asyncio.create_task(executor.reconcile(queued_id))
        await asyncio.sleep(0)
        applying = asyncio.create_task(executor.apply(queued_id))
        await asyncio.sleep(0)
        await executor.decline(queued_id)
        _ApplyHandler.release.set()
        results = await asyncio.gather(active, reconciling, applying, return_exceptions=True)
        await executor.wait_idle()
        return results

    @staticmethod
    async def _decline_claimed_reconciliation(
        executor: ApplyExecutor,
        job_id: uuid.UUID,
    ) -> tuple[BaseException, list[BaseException | None]]:
        """Attempt Decline after reconciliation has claimed and entered the handler.

        Args:
            executor: Apply runtime under test.
            job_id: Completed job identifier.

        Returns:
            Decline failure and results from reconciliation and explicit Apply.
        """
        reconciling = asyncio.create_task(executor.reconcile(job_id))
        await asyncio.wait_for(_ApplyHandler.applied.wait(), 2)
        applying = asyncio.create_task(executor.apply(job_id))
        await asyncio.sleep(0)
        decline_error = (await asyncio.gather(executor.decline(job_id), return_exceptions=True))[0]
        _ApplyHandler.release.set()
        results = await asyncio.gather(reconciling, applying, return_exceptions=True)
        await executor.wait_idle()
        return decline_error, results

    @staticmethod
    async def _decline_failed_apply_behind_blocked_job(
        executor: ApplyExecutor,
        active_id: uuid.UUID,
        failed_id: uuid.UUID,
    ) -> None:
        """Decline a failed Apply while an earlier job owns the FIFO lane.

        Args:
            executor: Apply runtime under test.
            active_id: Job blocking the FIFO worker.
            failed_id: Failed Apply with a durable recovery receipt.
        """
        active = asyncio.create_task(executor.apply(active_id))
        await asyncio.wait_for(_ApplyHandler.applied.wait(), 2)
        executor.request_reconcile(failed_id)
        await asyncio.sleep(0)
        declined = asyncio.create_task(executor.decline(failed_id))
        await asyncio.sleep(0)
        _ApplyHandler.release.set()
        await asyncio.gather(active, declined)
        await executor.wait_idle()

    @staticmethod
    async def _complete_during_stale_reconciliation(
        interface: _PausedSnapshotQueue,
        executor: ApplyExecutor,
        job_id: uuid.UUID,
        value: int,
    ) -> None:
        """Complete one job after active reconciliation has read its prior state.

        Args:
            interface: Real SQLite queue with a paused snapshot read.
            executor: Apply runtime under test.
            job_id: In-progress job identifier.
            value: Completed output value.
        """
        reconciling = asyncio.create_task(executor.reconcile(job_id))
        snapshot_read = await asyncio.to_thread(interface.snapshot_read.wait, 2)
        if not snapshot_read:
            raise RuntimeError("Timed out waiting for reconciliation to read the stale snapshot")
        interface.complete_job(job_id, JobOutputs({VALUE: value}))
        await asyncio.sleep(0)
        interface.resume_snapshot.set()
        await reconciling
        await executor.wait_idle()

    @staticmethod
    async def _recover_apply_interrupted_after_external_mutation(
        interface: QueueInterface,
        executor: ApplyExecutor,
        job: _ApplyJob,
    ) -> None:
        """Simulate a crash after mutation, then retry and revert from the durable receipt.

        Args:
            interface: Durable queue whose active Apply operation is interrupted.
            executor: Restarted Apply runtime used for retry and Revert.
            job: Completed job whose output is applied.
        """
        binding = job.apply_binding
        assert binding is not None
        handler = _ApplyHandler()
        receipt = await handler.capture_receipt(job.value, binding.target)
        claimed = interface.start_apply_operation(
            job.job_id,
            (ApplyDisposition.PENDING,),
            (ApplyOperation.IDLE,),
            ApplyOperation.APPLYING,
        )
        if not claimed:
            raise RuntimeError("Could not claim the simulated interrupted Apply")
        persisted = interface.persist_apply_receipt(job.job_id, ApplyOperation.APPLYING, receipt)
        if not persisted:
            raise RuntimeError("Could not persist the simulated interrupted Apply receipt")
        await handler.apply(job.value, binding.target, receipt)
        interface.recover_interrupted_jobs()
        await executor.apply(job.job_id)
        await executor.revert(job.job_id)

    async def test_apply_persists_captured_receipt_before_external_mutation(self):
        """Apply observes its exact receipt durably stored while the operation is active."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface, value=7)
            observed = []
            _ApplyHandler.before_mutation = lambda receipt: observed.append(
                (
                    receipt,
                    interface.get_apply_receipt(job.job_id),
                    interface.get_job_snapshot(job.job_id).apply_operation,
                    _ApplyHandler.target_values["asset"],
                )
            )

            # Act
            await executor.apply(job.job_id)

            # Assert
            receipt = _Receipt(original=100, applied=7)
            self.assertEqual(_ApplyHandler.captures, [receipt])
            self.assertEqual(observed, [(receipt, receipt, ApplyOperation.APPLYING, 100)])
            self.assertEqual(_ApplyHandler.calls, [("apply", receipt)])

    async def test_active_apply_receipt_cannot_overwrite_original_baseline(self):
        """The first durable receipt remains immutable throughout an active Apply attempt."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = self._complete(interface, value=7)
            self.assertTrue(
                interface.start_apply_operation(
                    job.job_id,
                    (ApplyDisposition.PENDING,),
                    (ApplyOperation.IDLE,),
                    ApplyOperation.APPLYING,
                )
            )
            original = _Receipt(original=100, applied=7)
            self.assertTrue(interface.persist_apply_receipt(job.job_id, ApplyOperation.APPLYING, original))

            # Act
            overwritten = interface.persist_apply_receipt(
                job.job_id,
                ApplyOperation.APPLYING,
                _Receipt(original=7, applied=7),
            )

            # Assert
            self.assertFalse(overwritten)
            self.assertEqual(interface.get_apply_receipt(job.job_id), original)

    async def test_interrupted_apply_retry_preserves_original_baseline(self):
        """Retry after a crash-window mutation reuses the receipt captured before that mutation."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface, value=7)

            # Act
            await self._recover_apply_interrupted_after_external_mutation(interface, executor, job)

            # Assert
            receipt = _Receipt(original=100, applied=7)
            self.assertEqual(_ApplyHandler.captures, [receipt])
            self.assertEqual(_ApplyHandler.calls, [("apply", receipt), ("apply", receipt), ("revert", receipt)])
            self.assertEqual(_ApplyHandler.target_values["asset"], 100)
            self.assertIsNone(interface.get_apply_receipt(job.job_id))

    async def test_apply_pending_output_persists_durable_receipt(self):
        """First Apply stores the exact durable handler receipt."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface, value=7)

            # Act
            await executor.apply(job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.APPLIED)
            self.assertIs(snapshot.apply_operation, ApplyOperation.IDLE)
            self.assertEqual(interface.get_apply_receipt(job.job_id), _Receipt(original=100, applied=7))

    async def test_reapply_applied_output_receives_prior_receipt(self):
        """Reapply passes the first durable receipt back to the handler."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface, value=7)
            await executor.apply(job.job_id)
            prior_receipt = interface.get_apply_receipt(job.job_id)
            _ApplyHandler.calls.clear()

            # Act
            await executor.apply(job.job_id)

            # Assert
            self.assertEqual(_ApplyHandler.calls, [("apply", prior_receipt)])
            self.assertEqual(interface.get_apply_receipt(job.job_id), prior_receipt)

    async def test_revert_applied_output_clears_receipt_and_declines(self):
        """Successful Revert clears the stale receipt and declines the output."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface, value=7)
            await executor.apply(job.job_id)
            receipt = interface.get_apply_receipt(job.job_id)
            _ApplyHandler.calls.clear()

            # Act
            await executor.revert(job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertEqual(_ApplyHandler.calls, [("revert", receipt)])
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.DECLINED)
            self.assertIs(snapshot.apply_operation, ApplyOperation.IDLE)
            self.assertIsNone(interface.get_apply_receipt(job.job_id))

    async def test_missing_receipt_codec_rejects_apply_binding_submission_atomically(self):
        """Apply work cannot enter the queue before every exact lifecycle type is registered."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = _ApplyJob(
                apply_binding=ApplyBinding(output_port=VALUE, handler_type=_ApplyHandler, target=_Target("asset"))
            )
            persistence.get_registry().unregister_codecs([_RECEIPT_CODEC])
            try:
                # Act
                with self.assertRaisesRegex(RuntimeError, "Receipt"):
                    interface.submit(job)

                # Assert
                self.assertEqual(interface.get_graph_snapshots(), [])
                self.assertEqual(list(interface.iter_snapshot()), [])
            finally:
                persistence.get_registry().register_codecs([_RECEIPT_CODEC])

    async def test_apply_failure_preserves_disposition_and_receipt_without_automatic_retry(self):
        """Operation failure is durable and reconciliation never retries it automatically."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry, auto_apply_enabled=lambda: True)
            self.executor = executor
            job = self._complete(interface)
            _ApplyHandler.fail = True

            # Act
            error = await self._fail_and_reconcile(executor, job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIsInstance(error, ValueError)
            self.assertEqual(str(error), "apply failed")
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.PENDING)
            self.assertIs(snapshot.apply_operation, ApplyOperation.APPLY_FAILED)
            self.assertEqual(snapshot.apply_reason, "The output could not be applied.")
            self.assertEqual(snapshot.apply_error.message, "apply failed")
            self.assertNotIn("apply failed", snapshot.apply_reason)
            self.assertEqual(interface.get_apply_receipt(job.job_id), _Receipt(100, 1))
            self.assertEqual(len(_ApplyHandler.calls), 1)

    async def test_decline_after_apply_mutation_failure_reverts_before_recording_declined(self):
        """Decline restores a potentially mutated target through its durable receipt."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface, value=7)
            _ApplyHandler.fail_after_mutation = True
            with self.assertRaisesRegex(ValueError, "apply failed after mutation"):
                await executor.apply(job.job_id)
            self.assertEqual(_ApplyHandler.target_values["asset"], 7)
            receipt = interface.get_apply_receipt(job.job_id)
            _ApplyHandler.calls.clear()

            # Act
            await executor.decline(job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertEqual(_ApplyHandler.calls, [("revert", receipt)])
            self.assertEqual(_ApplyHandler.target_values["asset"], 100)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.DECLINED)
            self.assertIs(snapshot.apply_operation, ApplyOperation.IDLE)
            self.assertIsNone(interface.get_apply_receipt(job.job_id))

    async def test_decline_promotes_queued_reconciliation_to_revert_after_failed_apply(self):
        """Decline promotes an unclaimed reconciliation without retaining its cancellation flag."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            failed = self._complete(interface, value=7)
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            _ApplyHandler.fail = True
            with self.assertRaisesRegex(ValueError, "apply failed"):
                await executor.apply(failed.job_id)
            _ApplyHandler.fail = False
            _ApplyHandler.calls.clear()
            blocker = self._complete(interface, value=1)
            _ApplyHandler.applied = asyncio.Event()
            _ApplyHandler.release = asyncio.Event()

            # Act
            await self._decline_failed_apply_behind_blocked_job(
                executor,
                blocker.job_id,
                failed.job_id,
            )

            # Assert
            snapshot = interface.get_job_snapshot(failed.job_id)
            self.assertEqual([call[0] for call in _ApplyHandler.calls], ["apply", "revert"])
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.DECLINED)
            self.assertIs(snapshot.apply_operation, ApplyOperation.IDLE)
            self.assertIsNone(interface.get_apply_receipt(failed.job_id))

    async def test_direct_decline_rejects_failed_apply_with_recovery_receipt(self):
        """Persistence cannot bypass receipt-based recovery and report the output as declined."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface)
            _ApplyHandler.fail = True
            with self.assertRaises(ValueError):
                await executor.apply(job.job_id)
            receipt = interface.get_apply_receipt(job.job_id)

            # Act
            declined = interface.decline_apply(job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertFalse(declined)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.PENDING)
            self.assertIs(snapshot.apply_operation, ApplyOperation.APPLY_FAILED)
            self.assertEqual(interface.get_apply_receipt(job.job_id), receipt)

    async def test_declined_apply_failure_returns_to_pending_for_safe_recovery(self):
        """A failed retry cannot report Declined while its durable receipt may own a mutation."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface)

            # Act
            error = await self._decline_then_fail_apply(executor, job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertEqual(str(error), "apply failed")
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.PENDING)
            self.assertIs(snapshot.apply_operation, ApplyOperation.APPLY_FAILED)
            self.assertEqual(snapshot.apply_reason, "The output could not be applied.")

    async def test_explicit_apply_promoting_an_in_flight_reconcile_still_applies(self):
        """An explicit Apply that promotes a running reconcile must apply, not resolve the caller with no result."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface)

            # Hold the automatic reconcile inside binding resolution, which is where the promotion used to be missed.
            reached_binding = asyncio.Event()
            release_binding = asyncio.Event()
            original_get_binding = executor._get_handler_binding

            async def _paused_get_binding(job_id, handler_id):
                reached_binding.set()
                await release_binding.wait()
                return await original_get_binding(job_id, handler_id)

            # Act
            with mock.patch.object(executor, "_get_handler_binding", _paused_get_binding):
                executor.request_reconcile(job.job_id)
                await reached_binding.wait()
                apply_task = asyncio.ensure_future(executor.apply(job.job_id))
                await asyncio.sleep(0)
                release_binding.set()
                await apply_task

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.APPLIED)
            self.assertIn("apply", [call[0] for call in _ApplyHandler.calls])

    async def test_explicit_apply_promoting_a_reconcile_reports_binding_failure(self):
        """A promoted Apply must receive a binding failure that an automatic reconciliation would ignore."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface)
            reached_binding = asyncio.Event()
            release_binding = asyncio.Event()

            async def _paused_failing_get_binding(_job_id, _handler_id):
                reached_binding.set()
                await release_binding.wait()
                raise RuntimeError("the handler is unavailable")

            # Act
            with mock.patch.object(executor, "_get_handler_binding", _paused_failing_get_binding):
                executor.request_reconcile(job.job_id)
                await reached_binding.wait()
                apply_task = asyncio.ensure_future(executor.apply(job.job_id))
                await asyncio.sleep(0)
                release_binding.set()

                # Assert
                with self.assertRaises(RuntimeError) as raised:
                    await apply_task
            self.assertEqual(str(raised.exception), "the handler is unavailable")

    async def test_reapply_is_available_after_revert_failure(self):
        """A failed Revert preserves the receipt and does not block Reapply."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface, value=4)

            # Act
            error = await self._recover_reapply_after_failed_revert(executor, job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertEqual(str(error), "revert failed")
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.APPLIED)
            self.assertIs(snapshot.apply_operation, ApplyOperation.IDLE)
            self.assertIsNone(snapshot.apply_reason)
            self.assertEqual(interface.get_apply_receipt(job.job_id), _Receipt(100, 4))

    async def test_revert_is_available_after_reapply_failure(self):
        """A failed Reapply preserves the receipt and still permits a guarded Revert."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface, value=4)
            await executor.apply(job.job_id)
            receipt = interface.get_apply_receipt(job.job_id)
            _ApplyHandler.fail = True
            with self.assertRaises(ValueError):
                await executor.apply(job.job_id)
            _ApplyHandler.fail = False
            self.assertIs(interface.get_job_snapshot(job.job_id).apply_operation, ApplyOperation.REAPPLY_FAILED)
            _ApplyHandler.calls.clear()

            # Act
            await executor.revert(job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertEqual(_ApplyHandler.calls, [("revert", receipt)])
            self.assertEqual(_ApplyHandler.target_values["asset"], 100)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.DECLINED)
            self.assertIs(snapshot.apply_operation, ApplyOperation.IDLE)
            self.assertIsNone(interface.get_apply_receipt(job.job_id))

    async def test_apply_mutations_run_sequentially_in_fifo_order(self):
        """Concurrent callers share one single-overlap main-loop mutation lane."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            first = self._complete(interface, value=1)
            second = self._complete(interface, value=2)
            _ApplyHandler.release = asyncio.Event()

            # Act
            calls_before_release, peak = await self._apply_two_jobs(executor, first.job_id, second.job_id)

            # Assert
            self.assertEqual(calls_before_release, 1)
            self.assertEqual(peak, 1)
            self.assertEqual([call[0] for call in _ApplyHandler.calls], ["apply", "apply"])

    async def test_concurrent_explicit_apply_callers_share_one_exact_job_operation(self):
        """Two views checking one output invoke its real handler only once without Reapply."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface, value=7)
            _ApplyHandler.release = asyncio.Event()

            # Act
            await self._apply_one_job_from_two_callers(executor, job.job_id)

            # Assert
            self.assertEqual(_ApplyHandler.calls, [("apply", _Receipt(100, 7))])
            self.assertEqual(_ApplyHandler.target_values["asset"], 7)

    async def test_explicit_apply_promotes_queued_manual_reconciliation_without_reapply(self):
        """Explicit Apply promotes earlier manual reconciliation into one handler call."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            active = self._complete(interface, value=1)
            queued = self._complete(interface, value=2)
            executor = ApplyExecutor(interface, registry, auto_apply_enabled=lambda: False)
            self.executor = executor
            _ApplyHandler.release = asyncio.Event()

            # Act
            results = await self._coordinate_blocked_apply_requests(
                executor,
                active.job_id,
                queued.job_id,
                reconcile_first=True,
            )

            # Assert
            self.assertEqual(results, [None, None, None])
            self.assertEqual(
                _ApplyHandler.calls,
                [("apply", _Receipt(100, 1)), ("apply", _Receipt(1, 2))],
            )
            self.assertIs(interface.get_job_snapshot(queued.job_id).apply_disposition, ApplyDisposition.APPLIED)

    async def test_explicit_apply_joins_queued_automatic_reconciliation_without_reapply(self):
        """Explicit Apply joins earlier automatic reconciliation behind blocked lane work."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            active = self._complete(interface, value=1)
            queued = self._complete(interface, value=2)
            _ApplyHandler.apply_policy = ApplyPolicy.ALWAYS_AUTOMATIC
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            _ApplyHandler.release = asyncio.Event()

            # Act
            results = await self._coordinate_blocked_apply_requests(
                executor,
                active.job_id,
                queued.job_id,
                reconcile_first=True,
            )

            # Assert
            self.assertEqual(results, [None, None, None])
            self.assertEqual(
                _ApplyHandler.calls,
                [("apply", _Receipt(100, 1)), ("apply", _Receipt(1, 2))],
            )

    async def test_reconciliation_joins_earlier_explicit_apply_without_second_handler_call(self):
        """Later reconciliation shares queued explicit Apply without adding work."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            active = self._complete(interface, value=1)
            queued = self._complete(interface, value=2)
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            _ApplyHandler.release = asyncio.Event()

            # Act
            results = await self._coordinate_blocked_apply_requests(
                executor,
                active.job_id,
                queued.job_id,
                reconcile_first=False,
            )

            # Assert
            self.assertEqual(results, [None, None, None])
            self.assertEqual(
                _ApplyHandler.calls,
                [("apply", _Receipt(100, 1)), ("apply", _Receipt(1, 2))],
            )

    async def test_explicit_apply_joins_active_reconciliation_and_notifications_coalesce(self):
        """Active automatic Apply and repeated wakes remain one exact-job mutation."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            job = self._complete(interface, value=7)
            _ApplyHandler.apply_policy = ApplyPolicy.ALWAYS_AUTOMATIC
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            _ApplyHandler.release = asyncio.Event()

            # Act
            results = await self._join_active_reconciliation(executor, job.job_id)

            # Assert
            self.assertEqual(results, [None, None])
            self.assertEqual(_ApplyHandler.calls, [("apply", _Receipt(100, 7))])
            self.assertIs(interface.get_job_snapshot(job.job_id).apply_disposition, ApplyDisposition.APPLIED)

    async def test_active_reconciliation_coalesces_completion_into_one_follow_up(self):
        """A completion arriving after a stale read triggers one fresh reconciliation."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = _PausedSnapshotQueue(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            job = _ApplyJob(
                value=7,
                apply_binding=ApplyBinding(output_port=VALUE, handler_type=_ApplyHandler, target=_Target("asset")),
            )
            interface.submit(job)
            interface.claim_runnable_jobs()
            interface.start_job(job.job_id)
            interface.pause_job_id = job.job_id
            _ApplyHandler.apply_policy = ApplyPolicy.ALWAYS_AUTOMATIC
            executor = ApplyExecutor(interface, registry)
            self.executor = executor

            # Act
            await self._complete_during_stale_reconciliation(interface, executor, job.job_id, 7)

            # Assert
            self.assertEqual(_ApplyHandler.calls, [("apply", _Receipt(100, 7))])
            self.assertIs(interface.get_job_snapshot(job.job_id).apply_disposition, ApplyDisposition.APPLIED)

    async def test_decline_cancels_queued_reconciliation_shared_with_explicit_apply(self):
        """Decline cancels one shared pre-claim request before either caller can Apply."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            active = self._complete(interface, value=1)
            queued = self._complete(interface, value=2)
            _ApplyHandler.apply_policy = ApplyPolicy.ALWAYS_AUTOMATIC
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            _ApplyHandler.release = asyncio.Event()

            # Act
            results = await self._decline_coordinated_queued_apply(executor, active.job_id, queued.job_id)

            # Assert
            self.assertIsNone(results[0])
            self.assertTrue(all(isinstance(result, RuntimeError) for result in results[1:]))
            self.assertTrue(all("cancelled by Decline" in str(result) for result in results[1:]))
            self.assertEqual(_ApplyHandler.calls, [("apply", _Receipt(100, 1))])
            self.assertIs(interface.get_job_snapshot(queued.job_id).apply_disposition, ApplyDisposition.DECLINED)

    async def test_decline_cannot_overwrite_claimed_reconciliation_joined_by_explicit_apply(self):
        """Decline fails cleanly once shared reconciliation owns durable Apply state."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            job = self._complete(interface, value=7)
            _ApplyHandler.apply_policy = ApplyPolicy.ALWAYS_AUTOMATIC
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            _ApplyHandler.release = asyncio.Event()

            # Act
            decline_error, results = await self._decline_claimed_reconciliation(executor, job.job_id)

            # Assert
            self.assertIsInstance(decline_error, RuntimeError)
            self.assertIn("not pending", str(decline_error))
            self.assertEqual(results, [None, None])
            self.assertEqual(_ApplyHandler.calls, [("apply", _Receipt(100, 7))])
            self.assertIs(interface.get_job_snapshot(job.job_id).apply_disposition, ApplyDisposition.APPLIED)

    async def test_cancelled_apply_waiter_does_not_release_active_exact_job_operation(self):
        """Cancelling one view cannot let another view enqueue Reapply behind active Apply."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface, value=7)
            _ApplyHandler.release = asyncio.Event()

            # Act
            await self._cancel_one_of_two_apply_callers(executor, job.job_id)

            # Assert
            self.assertEqual(_ApplyHandler.calls, [("apply", _Receipt(100, 7))])

    async def test_conflicting_explicit_operation_is_rejected_while_exact_job_is_reserved(self):
        """Revert cannot queue behind an active Apply for the same exact job."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface, value=7)
            _ApplyHandler.release = asyncio.Event()

            # Act
            completed_immediately, error = await self._conflict_with_active_apply(executor, job.job_id)

            # Assert
            self.assertTrue(completed_immediately)
            self.assertIsInstance(error, RuntimeError)
            self.assertIn("already has", str(error))
            self.assertEqual(_ApplyHandler.calls, [("apply", _Receipt(100, 7))])

    async def test_declined_user_state_wins_over_automatic_policy(self):
        """Reconciliation does not Apply an output explicitly declined by the user."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry, auto_apply_enabled=lambda: True)
            self.executor = executor
            job = self._complete(interface)

            # Act
            await self._decline_and_reconcile(executor, job.job_id)

            # Assert
            self.assertIs(interface.get_job_snapshot(job.job_id).apply_disposition, ApplyDisposition.DECLINED)
            self.assertEqual(_ApplyHandler.calls, [])

    async def test_missing_registered_handler_does_not_mutate_durable_apply_state(self):
        """Live handler absence does not replace the durable Apply operation."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface)

            # Act
            with self.assertRaisesRegex(RuntimeError, "handler.*unavailable"):
                await executor.apply(job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.PENDING)
            self.assertIs(snapshot.apply_operation, ApplyOperation.IDLE)
            self.assertIsNone(snapshot.apply_reason)
            self.assertFalse(executor.is_handler_available(job.job_id))

    async def test_worker_thread_completion_reconciles_automatic_policy_on_main_loop(self):
        """A worker-thread queue event safely wakes automatic Apply on the captured loop."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            _ApplyHandler.apply_policy = ApplyPolicy.ALWAYS_AUTOMATIC
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = _ApplyJob(
                value=9,
                apply_binding=ApplyBinding(output_port=VALUE, handler_type=_ApplyHandler, target=_Target("asset")),
            )
            interface.submit(job)
            interface.claim_runnable_jobs()
            interface.start_job(job.job_id)

            # Act
            await self._complete_from_worker_and_wait(executor, interface, job.job_id, 9)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.APPLIED)
            self.assertIs(snapshot.apply_operation, ApplyOperation.IDLE)
            self.assertEqual(interface.get_apply_receipt(job.job_id), _Receipt(100, 9))

    async def test_automatic_apply_waits_for_handler_prerequisite(self):
        """An unavailable product target stays ready without recording an Apply failure."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            _ApplyHandler.apply_policy = ApplyPolicy.ALWAYS_AUTOMATIC
            _ApplyHandler.block_reason = "Open the target project before applying this output."
            job = self._complete(interface, value=9)
            executor = ApplyExecutor(interface, registry)
            self.executor = executor

            # Act
            await executor.reconcile(job.job_id)

            # Assert
            waiting_snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(waiting_snapshot.apply_disposition, ApplyDisposition.PENDING)
            self.assertIs(waiting_snapshot.apply_operation, ApplyOperation.IDLE)
            self.assertIsNone(waiting_snapshot.apply_reason)
            self.assertEqual(_ApplyHandler.calls, [])

    async def test_automatic_apply_reconciles_after_handler_prerequisite_becomes_available(self):
        """A targeted reconciliation applies pending work after its product target becomes available."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            _ApplyHandler.apply_policy = ApplyPolicy.ALWAYS_AUTOMATIC
            _ApplyHandler.block_reason = "Open the target project before applying this output."
            job = self._complete(interface, value=9)
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            _ApplyHandler.block_reason = None

            # Act
            await executor.reconcile(job.job_id)

            # Assert
            applied_snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(applied_snapshot.apply_disposition, ApplyDisposition.APPLIED)
            self.assertIs(applied_snapshot.apply_operation, ApplyOperation.IDLE)
            self.assertEqual(_ApplyHandler.calls, [("apply", _Receipt(100, 9))])

    async def test_explicit_apply_refuses_blocked_handler_without_changing_state(self):
        """An explicit Apply reports a transient prerequisite without claiming or failing the job."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            _ApplyHandler.block_reason = "Open the target project before applying this output."
            job = self._complete(interface, value=9)
            executor = ApplyExecutor(interface, registry)
            self.executor = executor

            # Act
            with self.assertRaises(ApplyExecutionError) as error_context:
                await executor.apply(job.job_id)

            # Assert
            self.assertEqual(error_context.exception.reason, _ApplyHandler.block_reason)
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.PENDING)
            self.assertIs(snapshot.apply_operation, ApplyOperation.IDLE)
            self.assertIsNone(snapshot.apply_error)
            self.assertEqual(_ApplyHandler.calls, [])

    async def test_handler_registration_notifies_and_reconciles_automatic_pending_work(self):
        """Live registration refreshes consumers and reconciles automatic pending work."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            _ApplyHandler.apply_policy = ApplyPolicy.ALWAYS_AUTOMATIC
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface, value=5)
            changed = []
            subscription = interface.subscribe_schedule_conditions_changed(lambda: changed.append(None))
            with (
                mock.patch.object(handlers, "_registry", registry),
                mock.patch.object(handlers, "_apply_executor", executor),
                mock.patch.object(handlers, "_queue", interface),
            ):
                registry.set_changed_callback(handlers._on_apply_handlers_changed)
                # Act
                await self._register_and_wait(executor, [_ApplyHandler])

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertEqual(changed, [None])
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.APPLIED)
            self.assertIs(snapshot.apply_operation, ApplyOperation.IDLE)
            del subscription

    async def test_handler_unregistration_notifies_without_mutating_durable_apply_state(self):
        """Live unregistration refreshes consumers without replacing durable state."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            changed = []
            subscription = interface.subscribe_schedule_conditions_changed(lambda: changed.append(None))
            job = self._complete(interface)
            changed.clear()

            with (
                mock.patch.object(handlers, "_registry", registry),
                mock.patch.object(handlers, "_apply_executor", executor),
                mock.patch.object(handlers, "_queue", interface),
            ):
                registry.set_changed_callback(handlers._on_apply_handlers_changed)
                # Act
                handlers.unregister_plugins([_ApplyHandler])

            # Assert
            self.assertEqual(changed, [None])
            self.assertIs(interface.get_job_snapshot(job.job_id).apply_operation, ApplyOperation.IDLE)
            self.assertIsNone(registry.get_plugin_from_name(_ApplyHandler.name))
            del subscription

    async def test_shutdown_without_running_loop_settles_on_owning_loop(self):
        """Synchronous extension teardown settles async owners before returning."""
        # Arrange

        # Act
        result, scheduler_stop, executor_shutdown, registry = await asyncio.to_thread(
            self._shutdown_handlers_without_running_loop
        )

        # Assert
        self.assertIsNone(result)
        scheduler_stop.assert_awaited_once_with()
        executor_shutdown.assert_awaited_once_with()
        registry.set_changed_callback.assert_called_once_with(None)
        registry.destroy.assert_called_once_with()

    async def test_executor_creation_between_loop_ticks_captures_current_loop(self):
        """Hot-reload startup can create the executor between Kit loop ticks."""
        # Arrange

        # Act
        captured = await asyncio.to_thread(self._create_executor_without_running_loop)

        # Assert
        self.assertTrue(captured)

    async def test_cancelled_handler_settles_claimed_apply_failure(self):
        """Handler cancellation never leaves a durable Apply operation active."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface)
            _ApplyHandler.cancel = True

            # Act
            with self.assertRaisesRegex(RuntimeError, "cancelled"):
                await executor.apply(job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.apply_operation, ApplyOperation.APPLY_FAILED)
            self.assertEqual(snapshot.apply_error.exception_type, "CancelledError")
            self.assertEqual(snapshot.apply_reason, "The output could not be applied.")

    async def test_domain_apply_failure_separates_safe_reason_from_diagnostic(self):
        """A typed Apply failure persists its explicit safe reason beside raw diagnostics."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface)
            _ApplyHandler.domain_failure = True

            # Act
            with self.assertRaises(ApplyExecutionError):
                await executor.apply(job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertEqual(snapshot.apply_reason, "The selected project cannot accept this output.")
            self.assertEqual(snapshot.apply_error.message, "secret")
            self.assertNotIn("secret", snapshot.apply_reason)

    async def test_receipt_persistence_failure_prevents_external_mutation(self):
        """Receipt serialization failure settles Apply before invoking the handler mutation."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface)
            global _fail_receipt_encoding
            _fail_receipt_encoding = True

            # Act
            with self.assertRaisesRegex(TypeError, "receipt serialization failed"):
                await executor.apply(job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.apply_operation, ApplyOperation.APPLY_FAILED)
            self.assertIn("receipt serialization failed", snapshot.apply_error.message)
            self.assertEqual(_ApplyHandler.target_values["asset"], 100)
            self.assertEqual(_ApplyHandler.captures, [_Receipt(100, 1)])
            self.assertEqual(_ApplyHandler.calls, [])
            self.assertIsNone(interface.get_apply_receipt(job.job_id))

    async def test_raising_completion_listener_does_not_change_successful_apply(self):
        """Post-commit subscriber failure cannot change a successful Apply result."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            job = self._complete(interface, value=7)
            observed = []

            def raise_after_apply(changed_id: uuid.UUID) -> None:
                """Raise only after the durable Apply completion commit."""
                snapshot = interface.get_job_snapshot(changed_id)
                if snapshot.apply_disposition is ApplyDisposition.APPLIED:
                    raise ValueError("subscriber failed after commit")

            raising = interface.subscribe_job_changed(raise_after_apply)
            observing = interface.subscribe_job_changed(observed.append)
            executor = ApplyExecutor(interface, registry)
            self.executor = executor

            # Act
            with mock.patch("omni.flux.job_queue.core.interface.carb.log_error") as log_error:
                await executor.apply(job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.APPLIED)
            self.assertIs(snapshot.apply_operation, ApplyOperation.IDLE)
            self.assertEqual(_ApplyHandler.target_values["asset"], 7)
            self.assertEqual(_ApplyHandler.calls, [("apply", _Receipt(100, 7))])
            self.assertEqual(observed, [job.job_id, job.job_id])
            log_error.assert_called_once_with("Queue job-change subscriber failed: subscriber failed after commit")
            del raising, observing

    async def test_reapply_completion_failure_preserves_durable_receipt(self):
        """Failed Reapply completion preserves the original pre-mutation receipt."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface, value=7)
            await executor.apply(job.job_id)
            prior_receipt = interface.get_apply_receipt(job.job_id)
            _ApplyHandler.calls.clear()

            # Act
            with (
                mock.patch.object(interface, "complete_apply_operation", return_value=False),
                self.assertRaisesRegex(RuntimeError, "completion state changed"),
            ):
                await executor.apply(job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.APPLIED)
            self.assertIs(snapshot.apply_operation, ApplyOperation.REAPPLY_FAILED)
            self.assertEqual(interface.get_apply_receipt(job.job_id), prior_receipt)
            self.assertEqual(_ApplyHandler.target_values["asset"], 7)
            self.assertEqual(_ApplyHandler.calls, [("apply", prior_receipt)])

    async def test_reapply_reuses_durable_receipt_without_reserializing(self):
        """Reapply reuses the durable receipt without recapturing or serializing it."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface, value=7)
            await executor.apply(job.job_id)
            prior_receipt = interface.get_apply_receipt(job.job_id)
            _ApplyHandler.calls.clear()
            global _fail_receipt_encoding
            _fail_receipt_encoding = True

            # Act
            await executor.apply(job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.APPLIED)
            self.assertIs(snapshot.apply_operation, ApplyOperation.IDLE)
            self.assertEqual(interface.get_apply_receipt(job.job_id), prior_receipt)
            self.assertEqual(_ApplyHandler.target_values["asset"], 7)
            self.assertEqual(_ApplyHandler.calls, [("apply", prior_receipt)])

    async def test_revert_completion_failure_preserves_durable_receipt(self):
        """Failed Revert completion preserves the receipt for an idempotent retry."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface, value=7)
            await executor.apply(job.job_id)
            prior_receipt = interface.get_apply_receipt(job.job_id)
            _ApplyHandler.calls.clear()

            with mock.patch.object(interface, "complete_apply_operation", return_value=False):
                # Act
                with self.assertRaisesRegex(RuntimeError, "completion state changed"):
                    await executor.revert(job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.APPLIED)
            self.assertIs(snapshot.apply_operation, ApplyOperation.REVERT_FAILED)
            self.assertEqual(interface.get_apply_receipt(job.job_id), prior_receipt)
            self.assertEqual(_ApplyHandler.target_values["asset"], 100)
            self.assertEqual(_ApplyHandler.calls, [("revert", prior_receipt)])

    async def test_decline_cancels_same_job_apply_reserved_behind_active_lane_work(self):
        """Decline wins over a same-job Apply request that has not reached the FIFO worker."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            active = self._complete(interface, value=1)
            queued = self._complete(interface, value=2)
            _ApplyHandler.release = asyncio.Event()

            # Act
            error = await self._decline_queued_apply_behind_blocked_job(executor, active.job_id, queued.job_id)

            # Assert
            self.assertIsInstance(error, RuntimeError)
            self.assertIn("cancelled by Decline", str(error))
            self.assertIs(interface.get_job_snapshot(queued.job_id).apply_disposition, ApplyDisposition.DECLINED)
            self.assertEqual(_ApplyHandler.calls, [("apply", _Receipt(100, 1))])

    async def test_corrupt_outputs_after_claim_settle_apply_failure(self):
        """Output decoding failure after claim persists a failed Apply lifecycle."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            registry = ApplyHandlerRegistry()
            self.registry = registry
            registry.register_plugins([_ApplyHandler])
            executor = ApplyExecutor(interface, registry)
            self.executor = executor
            job = self._complete(interface)
            with interface.connection() as connection:
                connection.execute(
                    "UPDATE jobs SET outputs = ? WHERE job_id = ?",
                    (serialize({"unexpected": 1}), str(job.job_id)),
                )
                connection.commit()

            # Act
            with self.assertRaisesRegex((TypeError, ValueError), "output"):
                await executor.apply(job.job_id)

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.apply_operation, ApplyOperation.APPLY_FAILED)
            self.assertIsNotNone(snapshot.apply_error)

    async def test_submission_persists_exact_stable_apply_handler_id(self):
        """The jobs table stores the handler identity without loading the job payload."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = self._complete(interface)

            # Act
            with interface.connection() as connection:
                handler_id = connection.execute(
                    "SELECT apply_handler_id FROM jobs WHERE job_id = ?", (str(job.job_id),)
                ).fetchone()[0]

            # Assert
            self.assertEqual(handler_id, _ApplyHandler.name)

    async def test_submission_rejects_mismatched_handler_persistence_identity(self):
        """Handler classes cannot register a second stable persistence name."""
        # Arrange
        async with self._temp_db_path() as db_path:
            registry = persistence.get_registry()
            registry.unregister_codecs([_APPLY_HANDLER_CODEC])
            registry.register_codecs([_MISMATCHED_APPLY_HANDLER_CODEC])
            interface = QueueInterface(db_path)
            job = _ApplyJob(
                value=7,
                apply_binding=ApplyBinding(VALUE, _ApplyHandler, _Target("asset")),
            )
            try:
                # Act
                with self.assertRaisesRegex(QueueSubmissionError, "persistence name must match"):
                    interface.submit(job)

                # Assert
                self.assertEqual(list(interface.iter_snapshot()), [])
            finally:
                registry.unregister_codecs([_MISMATCHED_APPLY_HANDLER_CODEC])
                registry.register_codecs([_APPLY_HANDLER_CODEC])

    async def test_recovery_records_apply_interruption_reason_and_error(self):
        """Restart recovery converts active Apply work into a diagnosed user-facing failure."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = self._complete(interface)
            interface.start_apply_operation(
                job.job_id,
                (ApplyDisposition.PENDING,),
                (ApplyOperation.IDLE,),
                ApplyOperation.APPLYING,
            )

            # Act
            interface.recover_interrupted_jobs()

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.apply_operation, ApplyOperation.APPLY_FAILED)
            self.assertEqual(snapshot.apply_error.exception_type, "InterruptedError")
            self.assertIn("application stopped", snapshot.apply_reason)

    async def test_recovery_moves_interrupted_declined_apply_to_pending(self):
        """Restart cannot report Declined when an interrupted retry may have changed its target."""
        # Arrange
        async with self._temp_db_path() as db_path:
            interface = QueueInterface(db_path)
            job = self._complete(interface)
            self.assertTrue(interface.decline_apply(job.job_id))
            self.assertTrue(
                interface.start_apply_operation(
                    job.job_id,
                    (ApplyDisposition.DECLINED,),
                    (ApplyOperation.IDLE,),
                    ApplyOperation.APPLYING,
                )
            )

            # Act
            interface.recover_interrupted_jobs()

            # Assert
            snapshot = interface.get_job_snapshot(job.job_id)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.PENDING)
            self.assertIs(snapshot.apply_operation, ApplyOperation.APPLY_FAILED)

    async def test_registry_notifies_after_exact_registration_changes(self):
        """Registry consumers observe each completed live registration change."""
        # Arrange
        registry = ApplyHandlerRegistry()
        observed = []
        registry.set_changed_callback(lambda: observed.append(registry.get_plugin_from_name(_ApplyHandler.name)))

        # Act
        registry.register_plugins([_ApplyHandler])
        registry.unregister_plugins([_ApplyHandler])

        # Assert
        self.assertEqual(observed, [_ApplyHandler, None])
