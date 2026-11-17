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

__all__ = ["AssetModifierJob"]

import dataclasses
from typing import Any

from omni.flux.job_queue.core.job import Job, JobInputs


@dataclasses.dataclass
class AssetModifierJob(Job):
    """Hold the source and input values that the core fills for one source model.

    A subclass is a plain Job Queue job: it declares its own output ports and implements `execute()`, which is the
    transform. `output_url` is the job's own folder in the project's ingested assets, or None without a saved project.
    """

    context_name: str = ""
    source_url: str = ""
    prim_paths: tuple[str, ...] = ()
    values: dict[str, Any] = dataclasses.field(default_factory=dict)
    output_url: str | None = None

    def get_owned_output_urls(self) -> tuple[str, ...]:
        """Return the published folder that this job owns."""
        return (self.output_url,) if self.output_url else ()

    def get_input_urls(self, _inputs: JobInputs) -> tuple[str, ...]:
        """Return the source model that this job uses."""
        return (self.source_url,)
