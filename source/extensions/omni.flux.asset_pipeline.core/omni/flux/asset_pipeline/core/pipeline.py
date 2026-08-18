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

__all__ = [
    "PipelineProgressCallback",
    "PipelineValidationError",
    "run_pipeline",
    "validate_pipeline",
]

from collections.abc import Awaitable, Callable, Iterable

from .pipeline_context import PipelineContext, PipelineStepState
from .pipeline_step import PipelineStep

PipelineProgressCallback = Callable[[PipelineStep, int, int], Awaitable[None]]


class PipelineValidationError(ValueError):
    """Raised when a pipeline cannot run against the supplied context."""

    def __init__(self, errors: list[str]):
        """Build one validation error from ordered user-readable messages.

        Args:
            errors: Validation messages collected before execution.
        """
        self.errors = errors
        super().__init__("\n".join(errors))


def validate_pipeline(steps: Iterable[PipelineStep], context: PipelineContext) -> None:
    """Validate a step list before execution.

    This catches authoring-time mistakes such as duplicate step names, wrong
    context classes, or incompatible item types before any step mutates data.

    Args:
        steps: Configured steps to validate in execution order.
        context: State shared by the configured steps.

    Raises:
        PipelineValidationError: If any configured step is invalid for the context.
    """
    errors: list[str] = []
    seen_names: set[str] = set()

    for step in steps:
        if step.name in seen_names:
            errors.append(f"{step.name}: duplicate step name")
        seen_names.add(step.name)

        if step.enabled:
            errors.extend(step.validate(context))

    if errors:
        raise PipelineValidationError(errors)


async def run_pipeline(
    steps: Iterable[PipelineStep],
    context: PipelineContext,
    *,
    on_step_started: PipelineProgressCallback | None = None,
) -> None:
    """Validate and run enabled steps in order while recording execution state.

    Args:
        steps: Configured steps in execution order.
        context: State shared by all pipeline steps.
        on_step_started: Async callback awaited before each runnable step.

    Raises:
        PipelineValidationError: If the configured steps cannot run against the context.
        Exception: If a progress callback or pipeline step fails. The failure is recorded in the step state.
    """
    ordered_steps = list(steps)
    validate_pipeline(ordered_steps, context)
    total = len(ordered_steps)

    for index, step in enumerate(ordered_steps, start=1):
        if not step.enabled:
            context.execution_state[step.name] = PipelineStepState(
                step_name=step.name,
                was_skipped=True,
                skip_reason="disabled",
            )
            continue

        if not step.should_run(context):
            context.execution_state[step.name] = PipelineStepState(
                step_name=step.name,
                was_skipped=True,
                skip_reason=step.skip_reason(context),
            )
            continue

        try:
            if on_step_started is not None:
                await on_step_started(step, index, total)
            await step.run(context)
        except Exception as error:
            context.execution_state[step.name] = PipelineStepState(
                step_name=step.name,
                error=f"{type(error).__name__}: {error}",
            )
            raise

        context.execution_state[step.name] = PipelineStepState(step_name=step.name, did_run=True)
