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

__all__ = ["PipelineContext", "PipelineStepState"]

from dataclasses import dataclass, field
from typing import Generic, TypeVar

from .pipeline_item import PipelineItem

PipelineItemT = TypeVar("PipelineItemT", bound=PipelineItem)


@dataclass
class PipelineStepState:
    """Recorded state for one step during one pipeline run.

    This is for status, debugging, and explaining sparse execution. It is not
    rollback history. ``did_run`` means a step completed successfully. If
    ``error`` is set, the step did not complete and may still have partial
    forward-only side effects.
    """

    step_name: str
    did_run: bool = False
    was_skipped: bool = False
    skip_reason: str = ""
    error: str = ""


@dataclass
class PipelineContext(Generic[PipelineItemT]):
    """Shared state that flows through a pipeline of steps.

    Subclass to add product-specific fields (e.g., prim_paths, project_path).
    """

    items: list[PipelineItemT] = field(default_factory=list)
    execution_state: dict[str, PipelineStepState] = field(default_factory=dict)
