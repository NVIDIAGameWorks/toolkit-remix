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

__all__ = ["PipelineStep"]

import abc
from typing import ClassVar

from .pipeline_context import PipelineContext
from .pipeline_item import PipelineItem


class PipelineStep(abc.ABC):
    """One explicit, typed, idempotent pipeline step.

    ``validate()`` is for compatibility/configuration errors before mutation.
    ``should_run()`` is only for no-op checks after validation succeeds.
    ``run()`` mutates existing items/typed child records in place.
    """

    context_type: ClassVar[type[PipelineContext]] = PipelineContext
    item_types: ClassVar[tuple[type[PipelineItem], ...]] = ()
    idempotent: ClassVar[bool] = True

    def __init__(self):
        self.enabled: bool = True

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Return a unique identifier for this step."""

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Return a human-readable description of what this step does."""

    def validate(self, context: PipelineContext) -> list[str]:
        """Return deterministic, side-effect-free compatibility errors.

        Check context type, item type, required constructor config, required
        output directories, and invalid canonical ordering. Do not inspect or
        write files to decide whether work can be skipped.
        """
        errors: list[str] = []
        if not isinstance(context, self.context_type):
            errors.append(f"{self.name}: expected context {self.context_type.__name__}, got {type(context).__name__}")

        if not self.item_types:
            errors.append(f"{self.name}: must declare supported PipelineItem types")
            return errors

        for index, item in enumerate(context.items):
            if not isinstance(item, self.item_types):
                expected = ", ".join(item_type.__name__ for item_type in self.item_types)
                errors.append(f"{self.name}: item {index} expected {expected}, got {type(item).__name__}")

        return errors

    def should_run(self, context: PipelineContext) -> bool:
        """Return whether this already-compatible step has work left.

        False is valid for sparse execution, such as model steps in a texture-only
        run or DDS conversion when all textures already point to valid DDS files.
        It must never hide malformed input or missing configuration.
        """
        return True

    def skip_reason(self, context: PipelineContext) -> str:
        """Return the reason recorded when ``should_run()`` returns ``False``."""
        return "should_run returned False"

    @abc.abstractmethod
    async def run(self, context: PipelineContext) -> None:
        """Perform the step mutation idempotently."""
