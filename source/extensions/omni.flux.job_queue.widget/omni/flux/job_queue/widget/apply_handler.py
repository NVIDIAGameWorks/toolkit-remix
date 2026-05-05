"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import abc
import dataclasses
from typing import Any

import omni.flux.job_queue.core.events
import omni.flux.job_queue.core.interface
import omni.flux.job_queue.core.job


@dataclasses.dataclass
class CallbackApplied(omni.flux.job_queue.core.events.JobEvent):
    """
    Event recorded when job results have been applied.

    The context dict can be used to track different application contexts,
    allowing the same job to be applied multiple times in different contexts
    (e.g., different USD edit targets).
    """

    context: dict = dataclasses.field(default_factory=dict)


class ApplyHandler(abc.ABC):
    """
    Base class for handling job result application.

    ApplyHandlers are responsible for taking completed job results and
    applying them (e.g., to a USD stage). Each handler is registered for
    specific job types.

    Subclass this and implement can_handle() and apply() for your job type.
    """

    @classmethod
    @abc.abstractmethod
    def can_handle(cls, job: omni.flux.job_queue.core.job.Job) -> bool:
        """Check if this handler can process the given job type."""
        pass

    @abc.abstractmethod
    async def apply(
        self,
        interface: omni.flux.job_queue.core.interface.QueueInterface,
        job: omni.flux.job_queue.core.job.Job,
    ) -> None:
        """
        Apply the job results.

        Args:
            interface: The job queue interface for accessing job events/results.
            job: The completed job to apply results from.
        """
        pass

    def get_apply_context(self, job: omni.flux.job_queue.core.job.Job) -> dict[str, Any]:
        """
        Get context information for tracking applied state.

        Override this to provide context-specific information that determines
        whether the job has already been applied (e.g., current USD edit target).

        Returns an empty dict by default, meaning "applied once = applied everywhere".
        """
        return {}


class ApplyHandlerRegistry:
    """
    Registry for job apply handlers.

    Handlers are checked in registration order. The first handler that
    can_handle() the job type is used.

    This class provides the can_apply, has_been_applied, and apply functions
    that can be passed to CallbackExecutor.
    """

    _handlers: list[type[ApplyHandler]] = []

    @classmethod
    def register(cls, handler_class: type[ApplyHandler]) -> None:
        """Register an apply handler."""
        if handler_class not in cls._handlers:
            cls._handlers.append(handler_class)

    @classmethod
    def unregister(cls, handler_class: type[ApplyHandler]) -> None:
        """Unregister an apply handler."""
        if handler_class in cls._handlers:
            cls._handlers.remove(handler_class)

    @classmethod
    def clear(cls) -> None:
        """Remove all registered handlers."""
        cls._handlers.clear()

    @classmethod
    def get_handler(cls, job: omni.flux.job_queue.core.job.Job) -> ApplyHandler | None:
        """Get a handler instance for the given job, or None if no handler matches."""
        for handler_class in cls._handlers:
            if handler_class.can_handle(job):
                return handler_class()
        return None

    @classmethod
    def can_apply(cls, job: omni.flux.job_queue.core.job.Job) -> bool:
        """Check if any registered handler can apply this job."""
        return any(handler_class.can_handle(job) for handler_class in cls._handlers)

    @classmethod
    def has_been_applied(
        cls,
        interface: omni.flux.job_queue.core.interface.QueueInterface,
        job: omni.flux.job_queue.core.job.Job,
    ) -> bool:
        """
        Check if a job has already been applied in the current context.

        This checks for a CallbackApplied event and compares its context
        with the current context from the handler.
        """
        handler = cls.get_handler(job)
        if handler is None:
            return False

        event = interface.get_latest_event(job.job_id, CallbackApplied)
        if event is None:
            return False

        current_context = handler.get_apply_context(job)
        return event.context == current_context

    @classmethod
    async def apply(
        cls,
        interface: omni.flux.job_queue.core.interface.QueueInterface,
        job: omni.flux.job_queue.core.job.Job,
    ) -> None:
        """
        Apply job results using the appropriate handler.

        Also records a CallbackApplied event for has_been_applied tracking.

        Raises ValueError if no handler is registered for the job type.
        """
        handler = cls.get_handler(job)
        if handler is None:
            raise ValueError(f"No apply handler registered for job type: {type(job).__name__}")

        # Apply the job results
        await handler.apply(interface, job)

        # Record that we applied (for has_been_applied tracking)
        context = handler.get_apply_context(job)
        event = CallbackApplied(context=context)
        interface.append_event(job.job_id, event)
