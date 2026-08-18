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
import dataclasses
import uuid
from collections.abc import Callable

import carb
from omni.flux.utils.common import EventSubscription

from .apply_handler_base import ApplyHandler
from .apply_handler_registry import ApplyHandlerRegistry
from .enums import ApplyCommand, ApplyDisposition, ApplyOperation, ApplyPolicy, JobState
from .errors import ApplyExecutionError, JobError
from .interface import QueueInterface
from .job import ApplyBinding, value_matches_type

__all__ = ("ApplyExecutor",)


@dataclasses.dataclass(slots=True)
class _ApplyRequest:
    """Represent one FIFO Apply-lane request."""

    command: ApplyCommand
    job_id: uuid.UUID
    completion: asyncio.Future[BaseException | None] | None
    cancelled_by_decline: bool = False
    claimed: bool = False
    reconcile_again: bool = False


class ApplyExecutor:
    """Run all Apply, Reapply, and Revert work through one bounded FIFO lane."""

    def __init__(
        self,
        interface: QueueInterface,
        registry: ApplyHandlerRegistry,
        auto_apply_enabled: Callable[[], bool] | None = None,
    ) -> None:
        """Create an idle main-loop Apply lane.

        Args:
            interface: Persistent queue that owns Apply lifecycle state.
            registry: Explicit exact handler registry.
            auto_apply_enabled: Callback returning the global automatic setting.
        """
        self.interface = interface
        self.registry = registry
        self._auto_apply_enabled = auto_apply_enabled or (lambda: False)
        self._loop = asyncio.get_event_loop()
        self._requests: asyncio.Queue[_ApplyRequest] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._active_request: _ApplyRequest | None = None
        self._requests_by_job: dict[uuid.UUID, _ApplyRequest] = {}
        self._accepting = True
        self._subscription: EventSubscription | None = interface.subscribe_job_changed(self._on_job_changed)

    def is_handler_available(self, job_id: uuid.UUID) -> bool:
        """Return whether one job's exact configured handler is registered.

        Args:
            job_id: Job identifier.

        Returns:
            Whether the exact handler is available.
        """
        handler_id = self.interface.get_job_snapshot(job_id).apply_handler_id
        return handler_id is not None and self.registry.get_plugin_from_name(handler_id) is not None

    def get_apply_block_reason(self, job_id: uuid.UUID, operation: ApplyOperation) -> str | None:
        """Return why one exact registered handler cannot run an Apply operation.

        This is evaluated on demand for visible UI rows so transient product prerequisites stay current without
        polling or persisting an implicit Apply state.

        Args:
            job_id: Completed job identifier.
            operation: Exact Apply, Reapply, or Revert operation being considered.

        Returns:
            User-facing recovery guidance, or ``None`` when Apply can run.

        Raises:
            RuntimeError: If the job has no available exact handler.
            TypeError: If its persisted binding violates the registered handler contract.
        """
        snapshot = self.interface.get_job_snapshot(job_id)
        if snapshot.apply_handler_id is None:
            raise RuntimeError(f"Job {job_id} has no Apply binding")
        handler, binding = self._resolve_handler_binding(job_id, snapshot.apply_handler_id)
        return handler.get_apply_block_reason(binding.target, operation)

    async def apply(self, job_id: uuid.UUID) -> None:
        """Queue one explicit Apply or Reapply request.

        Args:
            job_id: Completed job identifier.
        """
        await self._submit(ApplyCommand.APPLY, job_id)

    async def decline(self, job_id: uuid.UUID) -> None:
        """Safely decline one output, reverting any potentially mutated target first.

        Args:
            job_id: Completed job identifier.

        Raises:
            RuntimeError: If the output cannot be declined or safely reverted.
        """
        request = self._requests_by_job.get(job_id)
        if (
            request is not None
            and request.command in (ApplyCommand.APPLY, ApplyCommand.RECONCILE)
            and not request.claimed
        ):
            request.cancelled_by_decline = True
        snapshot = await asyncio.to_thread(self.interface.get_job_snapshot, job_id)
        if snapshot.apply_operation in (ApplyOperation.APPLY_FAILED, ApplyOperation.REVERT_FAILED):
            receipt = await asyncio.to_thread(self.interface.get_apply_receipt, job_id)
            if receipt is not None:
                await self._submit(ApplyCommand.REVERT, job_id)
                return
        if not await asyncio.to_thread(self.interface.decline_apply, job_id):
            raise RuntimeError(f"Job {job_id} is not pending")

    async def revert(self, job_id: uuid.UUID) -> None:
        """Queue one explicit Revert request.

        Args:
            job_id: Applied job identifier.
        """
        await self._submit(ApplyCommand.REVERT, job_id)

    async def reconcile(self, job_id: uuid.UUID) -> None:
        """Queue one automatic-policy reconciliation request.

        Args:
            job_id: Changed job identifier.
        """
        await self._submit(ApplyCommand.RECONCILE, job_id)

    def request_reconcile(self, job_id: uuid.UUID) -> None:
        """Queue deduplicated reconciliation without creating waiter tasks.

        Args:
            job_id: Changed job identifier.
        """
        if not self._accepting:
            return
        if self._loop.is_closed():
            carb.log_error(f"Apply loop is closed; could not reconcile job {job_id}")
            return
        try:
            self._loop.call_soon_threadsafe(self._enqueue_reconcile, job_id)
        except RuntimeError as error:
            carb.log_error(f"Could not enqueue Apply reconciliation for job {job_id}: {error}")

    async def wait_idle(self) -> None:
        """Wait until all Apply-lane requests queued so far have settled.

        Raises:
            RuntimeError: If called outside the executor's owning event loop.
        """
        if asyncio.get_running_loop() is not self._loop:
            raise RuntimeError("Apply operations must run on the executor's event loop")
        await self._requests.join()

    async def shutdown(self) -> None:
        """Stop reconciliation after all queued and active Apply work settles."""
        self._accepting = False
        self._subscription = None
        worker = self._worker
        if worker is None:
            self._requests_by_job.clear()
            return
        await self._requests.join()
        self._requests_by_job.clear()
        self._worker = None
        worker.cancel()
        try:  # noqa: SIM105 - explicit worker cancellation must be awaited and acknowledged.
            await worker
        except asyncio.CancelledError:
            pass

    async def _submit(self, command: ApplyCommand, job_id: uuid.UUID) -> None:
        """Submit one bounded FIFO request and await its outcome.

        Args:
            command: Strongly typed Apply-lane command.
            job_id: Target job identifier.

        Raises:
            Exception: If request execution fails.
        """
        if asyncio.get_running_loop() is not self._loop:
            raise RuntimeError("Apply operations must run on the executor's event loop")
        if not self._accepting:
            raise RuntimeError("The Apply executor is shutting down")
        request = self._requests_by_job.get(job_id)
        if request is not None:
            can_promote_reconcile = request.command is ApplyCommand.RECONCILE and (
                command is ApplyCommand.APPLY
                or (command is ApplyCommand.REVERT and request is not self._active_request)
            )
            if can_promote_reconcile:
                request.command = command
                request.cancelled_by_decline = False
            elif command is not ApplyCommand.RECONCILE and command is not request.command:
                raise RuntimeError(f"Job {job_id} already has another explicit Apply request")
            completion = request.completion
            if completion is None:
                completion = asyncio.get_running_loop().create_future()
                request.completion = completion
        else:
            completion = asyncio.get_running_loop().create_future()
            request = _ApplyRequest(command, job_id, completion)
            self._requests_by_job[job_id] = request
            self._ensure_worker()
            self._requests.put_nowait(request)
        error = await asyncio.shield(completion)
        if isinstance(error, asyncio.CancelledError):
            raise RuntimeError("The Apply handler cancelled the operation")
        if error is not None:
            raise error

    def _enqueue_reconcile(self, job_id: uuid.UUID) -> None:
        """Deduplicate and enqueue one reconciliation on the captured main loop.

        Args:
            job_id: Changed job identifier.
        """
        if not self._accepting:
            return
        request = self._requests_by_job.get(job_id)
        if request is not None:
            if request is self._active_request:
                request.reconcile_again = True
            return
        self._ensure_worker()
        request = _ApplyRequest(ApplyCommand.RECONCILE, job_id, None)
        self._requests_by_job[job_id] = request
        self._requests.put_nowait(request)

    def _ensure_worker(self) -> None:
        """Create the single main-loop worker when needed."""
        if self._worker is None or self._worker.done():
            self._worker = asyncio.get_running_loop().create_task(self._run())

    async def _run(self) -> None:
        """Process bounded FIFO requests sequentially on the main loop.

        Raises:
            asyncio.CancelledError: When executor shutdown cancels the idle worker.
        """
        while True:
            request = await self._requests.get()
            self._active_request = request
            try:
                if request.cancelled_by_decline:
                    raise RuntimeError(f"Apply request for job {request.job_id} was cancelled by Decline")
                match request.command:
                    case ApplyCommand.APPLY:
                        await self._apply(request)
                    case ApplyCommand.REVERT:
                        await self._revert(request.job_id)
                    case ApplyCommand.RECONCILE:
                        await self._reconcile(request)
            except (Exception, asyncio.CancelledError) as error:  # noqa: BLE001 - FIFO requests must always settle.
                if request.completion is None:
                    if not request.cancelled_by_decline:
                        carb.log_error(f"Automatic Apply failed: {error}")
                elif not request.completion.done():
                    request.completion.set_result(_copy_request_error(error))
            else:
                if request.completion is not None and not request.completion.done():
                    request.completion.set_result(None)
            finally:
                self._active_request = None
                if self._requests_by_job.get(request.job_id) is request:
                    self._requests_by_job.pop(request.job_id)
                if request.reconcile_again and request.command is ApplyCommand.RECONCILE and not request.claimed:
                    self._enqueue_reconcile(request.job_id)
                self._requests.task_done()

    async def _apply(self, request: _ApplyRequest) -> None:
        """Execute one Apply or Reapply request from the FIFO worker.

        Args:
            request: Shared exact-job request being executed.

        Raises:
            RuntimeError: If durable state changes or the handler is unavailable.
            TypeError: If persisted types violate the exact handler contract.
            Exception: If product Apply fails.
            asyncio.CancelledError: If product Apply is cancelled.
        """
        job_id = request.job_id
        snapshot = await asyncio.to_thread(self.interface.get_job_snapshot, job_id)
        if snapshot.state is not JobState.DONE:
            raise RuntimeError(f"Job {job_id} is not complete")
        handler_id = snapshot.apply_handler_id
        if handler_id is None:
            raise RuntimeError(f"Job {job_id} has no Apply binding")
        if snapshot.apply_disposition in (ApplyDisposition.PENDING, ApplyDisposition.DECLINED):
            active_operation = ApplyOperation.APPLYING
            failure_operation = ApplyOperation.APPLY_FAILED
            allowed_operations = (
                ApplyOperation.IDLE,
                ApplyOperation.APPLY_FAILED,
            )
        elif snapshot.apply_disposition is ApplyDisposition.APPLIED:
            active_operation = ApplyOperation.REAPPLYING
            failure_operation = ApplyOperation.REAPPLY_FAILED
            allowed_operations = (
                ApplyOperation.IDLE,
                ApplyOperation.REAPPLY_FAILED,
                ApplyOperation.REVERT_FAILED,
            )
        else:
            raise RuntimeError(f"Job {job_id} is not ready to Apply")
        handler, binding = await self._get_handler_binding(job_id, handler_id)
        if block_reason := handler.get_apply_block_reason(binding.target, active_operation):
            raise ApplyExecutionError(
                block_reason,
                RuntimeError(f"Apply prerequisites are not satisfied for job {job_id}"),
            )
        if request.cancelled_by_decline:
            raise RuntimeError(f"Apply request for job {job_id} was cancelled by Decline")
        claimed = await asyncio.to_thread(
            self.interface.start_apply_operation,
            job_id,
            (snapshot.apply_disposition,),
            allowed_operations,
            active_operation,
        )
        if not claimed:
            if request.cancelled_by_decline:
                raise RuntimeError(f"Apply request for job {job_id} was cancelled by Decline")
            raise RuntimeError(f"Apply state changed for job {job_id}")
        request.claimed = True
        try:
            outputs = await asyncio.to_thread(self.interface.get_job_outputs, job_id)
            value = outputs[binding.output_port]
            if not value_matches_type(value, handler.input_type) or not value_matches_type(
                binding.target, handler.target_type
            ):
                raise TypeError("Apply value or target concrete type does not match the handler")
            receipt = await asyncio.to_thread(self.interface.get_apply_receipt, job_id)
            if receipt is None:
                if active_operation is ApplyOperation.REAPPLYING:
                    raise TypeError(f"Apply receipt must be exactly {handler.receipt_type.__name__}")
                receipt = await handler.capture_receipt(value, binding.target)
                if receipt is None or type(receipt) is not handler.receipt_type:
                    raise TypeError(f"Apply handler must capture exactly {handler.receipt_type.__name__}")
                persisted = await asyncio.to_thread(
                    self.interface.persist_apply_receipt,
                    job_id,
                    active_operation,
                    receipt,
                )
                if not persisted:
                    raise RuntimeError(f"Apply receipt state changed for job {job_id}")
            elif receipt is None or type(receipt) is not handler.receipt_type:
                raise TypeError(f"Apply receipt must be exactly {handler.receipt_type.__name__}")
            result = await handler.apply(value, binding.target, receipt)
            if result is not None:
                raise TypeError("Apply handler must return None")
            completed = await asyncio.to_thread(
                self.interface.complete_apply_operation,
                job_id,
                active_operation,
                ApplyDisposition.APPLIED,
            )
            if not completed:
                raise RuntimeError(f"Apply completion state changed for job {job_id}")
        except (Exception, asyncio.CancelledError) as error:
            failure_disposition = (
                ApplyDisposition.PENDING
                if snapshot.apply_disposition is ApplyDisposition.DECLINED
                else snapshot.apply_disposition
            )
            await self._settle_failure(job_id, active_operation, failure_operation, failure_disposition, error)
            raise

    async def _revert(self, job_id: uuid.UUID) -> None:
        """Execute one Revert request from the FIFO worker.

        Args:
            job_id: Applied job identifier.

        Raises:
            RuntimeError: If durable state changes or the handler is unavailable.
            TypeError: If persisted types violate the exact handler contract.
            Exception: If product Revert fails.
            asyncio.CancelledError: If product Revert is cancelled.
        """
        snapshot = await asyncio.to_thread(self.interface.get_job_snapshot, job_id)
        handler_id = snapshot.apply_handler_id
        if handler_id is None:
            raise RuntimeError(f"Job {job_id} has no Apply binding")
        if snapshot.apply_disposition is ApplyDisposition.APPLIED:
            allowed_operations = (ApplyOperation.IDLE, ApplyOperation.REAPPLY_FAILED, ApplyOperation.REVERT_FAILED)
        elif snapshot.apply_disposition in (ApplyDisposition.PENDING, ApplyDisposition.DECLINED):
            allowed_operations = (ApplyOperation.APPLY_FAILED, ApplyOperation.REVERT_FAILED)
        else:
            raise RuntimeError(f"Job {job_id} has no Apply result to revert")
        handler, binding = await self._get_handler_binding(job_id, handler_id)
        receipt = await asyncio.to_thread(self.interface.get_apply_receipt, job_id)
        if receipt is None or type(receipt) is not handler.receipt_type:
            raise TypeError(f"Apply receipt must be exactly {handler.receipt_type.__name__}")
        claimed = await asyncio.to_thread(
            self.interface.start_apply_operation,
            job_id,
            (snapshot.apply_disposition,),
            allowed_operations,
            ApplyOperation.REVERTING,
        )
        if not claimed:
            raise RuntimeError(f"Revert state changed for job {job_id}")
        try:
            value = (await asyncio.to_thread(self.interface.get_job_outputs, job_id))[binding.output_port]
            if not value_matches_type(value, handler.input_type) or not value_matches_type(
                binding.target, handler.target_type
            ):
                raise TypeError("Apply value or target concrete type does not match the handler")
            result = await handler.revert(value, binding.target, receipt)
            if result is not None:
                raise TypeError("Apply handler Revert must return None")
            completed = await asyncio.to_thread(
                self.interface.complete_apply_operation,
                job_id,
                ApplyOperation.REVERTING,
                ApplyDisposition.DECLINED,
                True,
            )
            if not completed:
                raise RuntimeError(f"Revert completion state changed for job {job_id}")
        except (Exception, asyncio.CancelledError) as error:
            await self._settle_failure(
                job_id,
                ApplyOperation.REVERTING,
                ApplyOperation.REVERT_FAILED,
                snapshot.apply_disposition,
                error,
            )
            raise

    async def _get_handler_binding(self, job_id: uuid.UUID, handler_id: str) -> tuple[ApplyHandler, ApplyBinding]:
        """Load one handler binding off the event loop.

        Args:
            job_id: Job whose persisted binding must be loaded.
            handler_id: Stable handler identity stored with the job snapshot.

        Returns:
            Instantiated exact handler and its typed binding.
        """
        return await asyncio.to_thread(self._resolve_handler_binding, job_id, handler_id)

    def _resolve_handler_binding(self, job_id: uuid.UUID, handler_id: str) -> tuple[ApplyHandler, ApplyBinding]:
        """Resolve and validate one job's exact registered handler binding.

        Args:
            job_id: Job whose persisted binding must be loaded.
            handler_id: Stable handler identity stored with the job snapshot.

        Returns:
            Instantiated exact handler and its typed binding.

        Raises:
            RuntimeError: If the exact handler is unavailable.
            TypeError: If the persisted binding or target violates the registered handler contract.
        """
        handler_type = self.registry.get_plugin_from_name(handler_id)
        if handler_type is None:
            raise RuntimeError(f"The Apply handler for job {job_id} is unavailable")
        handler = handler_type()
        job = self.interface.get_job(job_id)
        binding = job.apply_binding
        if binding is None or binding.handler_type is not handler_type or binding.handler_type.name != handler_id:
            raise TypeError(f"Job {job_id} Apply binding does not match its persisted handler identity")
        if not value_matches_type(binding.target, handler.target_type):
            raise TypeError("Apply target concrete type does not match the handler")
        return handler, binding

    async def _settle_failure(
        self,
        job_id: uuid.UUID,
        active_operation: ApplyOperation,
        failure_operation: ApplyOperation,
        failure_disposition: ApplyDisposition,
        error: BaseException,
    ) -> None:
        """Persist one post-claim failure while preserving its durable receipt.

        Args:
            job_id: Claimed job identifier.
            active_operation: Operation owned by this request.
            failure_operation: Durable failed operation state.
            failure_disposition: Stable disposition safe to expose after failure.
            error: Raised failure, optionally carrying an explicit safe reason.
        """
        diagnostic = error.diagnostic if isinstance(error, ApplyExecutionError) else error
        reason = error.reason if isinstance(error, ApplyExecutionError) else _apply_failure_reason(active_operation)
        await asyncio.to_thread(
            self.interface.fail_apply_operation,
            job_id,
            active_operation,
            failure_operation,
            failure_disposition,
            JobError.from_exception(diagnostic),
            reason,
        )

    async def _reconcile(self, request: _ApplyRequest) -> None:
        """Execute one automatic policy decision from the FIFO worker.

        Args:
            request: Shared exact-job request being reconciled.
        """
        job_id = request.job_id
        snapshot = await asyncio.to_thread(self.interface.get_job_snapshot, job_id)
        if request.cancelled_by_decline:
            raise RuntimeError(f"Apply request for job {job_id} was cancelled by Decline")
        if request.command is ApplyCommand.APPLY:
            await self._apply(request)
            return
        if (
            snapshot.state is not JobState.DONE
            or snapshot.apply_disposition is not ApplyDisposition.PENDING
            or snapshot.apply_operation is not ApplyOperation.IDLE
        ):
            return
        handler_id = snapshot.apply_handler_id
        if handler_id is None:
            return
        try:
            handler, binding = await self._get_handler_binding(job_id, handler_id)
        except RuntimeError:
            # A promotion can also land while a failing binding resolves. An automatic reconciliation has no caller and
            # stays silent, but a promoted explicit Apply must receive the failure instead of a successful result.
            if request.command is ApplyCommand.APPLY:
                raise
            return
        # An explicit Apply can promote this request while the binding resolves off the loop. Re-check the command, or
        # a manual policy returns here and the worker resolves the explicit caller with no result and no error.
        if request.command is ApplyCommand.APPLY:
            await self._apply(request)
            return
        policy = handler.apply_policy
        if policy is ApplyPolicy.ALWAYS_AUTOMATIC or (
            policy is ApplyPolicy.FOLLOW_GLOBAL and self._auto_apply_enabled()
        ):
            if handler.get_apply_block_reason(binding.target, ApplyOperation.APPLYING) is not None:
                return
            await self._apply(request)

    def _on_job_changed(self, job_id: uuid.UUID) -> None:
        """Queue targeted automatic reconciliation.

        Args:
            job_id: Changed job identifier.
        """
        self.request_reconcile(job_id)


def _apply_failure_reason(operation: ApplyOperation) -> str:
    """Return safe user-facing text for one failed Apply-lane operation.

    Args:
        operation: Active operation that failed.

    Returns:
        Operation-specific text that contains no diagnostic exception details.
    """
    if operation is ApplyOperation.REAPPLYING:
        return "The applied output could not be updated."
    if operation is ApplyOperation.REVERTING:
        return "The applied output could not be reverted."
    return "The output could not be applied."


def _copy_request_error(error: BaseException) -> BaseException:
    """Detach one caller-facing error from worker coroutine traceback state.

    Args:
        error: Failure caught by the FIFO worker.

    Returns:
        Equivalent error safe to raise in the submitting task.
    """
    if isinstance(error, ApplyExecutionError):
        return ApplyExecutionError(error.reason, error.diagnostic)
    if isinstance(error, asyncio.CancelledError):
        return asyncio.CancelledError(*error.args)
    try:
        return type(error)(*error.args)
    except (TypeError, ValueError):
        return RuntimeError(str(error))
