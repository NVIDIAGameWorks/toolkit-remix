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

__all__ = ["AssetModifierBase"]

import abc
from typing import ClassVar

from lightspeed.trex.asset_pipeline.core.jobs.asset_replace_apply_target import AssetReplaceApplyTarget
from omni.flux.factory.base import PluginBase
from omni.flux.job_queue.core.job import JobGraph
from pxr import Usd

from ..job import AssetModifierJob
from ..modifier_input import ModifierInput


class AssetModifierBase(PluginBase):
    """Declare a modifier: its name, inputs, accepted prims, and the Job Queue graph that runs its transform."""

    name: ClassVar[str]
    display_name: ClassVar[str]
    tooltip: ClassVar[str]
    experimental: ClassVar[bool] = False
    inputs: ClassVar[tuple[ModifierInput, ...]] = ()
    job_type: ClassVar[type[AssetModifierJob]]

    @abc.abstractmethod
    def is_compatible(self, prim: Usd.Prim) -> bool:
        """Return whether the modifier accepts the prim."""

    @abc.abstractmethod
    def build_graph(
        self, stage: Usd.Stage | None, graph: JobGraph, job: AssetModifierJob, target: AssetReplaceApplyTarget | None
    ) -> None:
        """Add the jobs that process and apply the job's output to the graph of one source model.

        The core built `job` from `job_type` with the source and input values, and added it to `graph`. `target` holds
        the source references to replace, or is None for a File Path Constant source. `stage` is None when no project
        is open. Set `job.skip_reason` to leave this source out of the submission.

        The job is saved in the queue, so values added to `job.values` must be serializable, such as scalars, strings,
        paths, and enums. Convert USD objects first, for example a prim to its path string.
        """
