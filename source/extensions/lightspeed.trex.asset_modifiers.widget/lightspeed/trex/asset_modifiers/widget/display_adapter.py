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

__all__ = ["AssetModifierDisplayAdapter"]

from lightspeed.trex.asset_modifiers.factory import AssetModifierJob
from omni.flux.job_queue.widget.display_adapter_base import JobDisplayAdapter


class AssetModifierDisplayAdapter(JobDisplayAdapter):
    """Show every modifier job's source in the Job Queue."""

    name = "asset_modifier"
    job_type = AssetModifierJob
    source_name = "Asset Modifiers"
    display_name = "Asset Modifier"

    def get_name_tooltip(self, job: AssetModifierJob) -> str:
        """Show the source prim paths or model path."""
        return "\n".join(job.prim_paths) or job.source_url

    def get_targets(self, job: AssetModifierJob) -> tuple[str, ...]:
        """Show the source prim paths, or the model path for a File Path Constant source."""
        return job.prim_paths or (job.source_url,)
