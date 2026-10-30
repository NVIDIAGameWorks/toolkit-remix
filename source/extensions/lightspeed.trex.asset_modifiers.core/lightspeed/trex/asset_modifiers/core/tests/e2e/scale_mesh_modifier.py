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

__all__ = ["ScaleMeshTestModifier"]

from lightspeed.trex.asset_modifiers.factory import AssetModifierBase, AssetModifierJob, ModifierInput
from lightspeed.trex.asset_modifiers.core.tests.e2e.scale_mesh_job import ScaleMeshTestJob
from lightspeed.trex.asset_pipeline.core.jobs import add_asset_optimization_jobs
from lightspeed.trex.asset_pipeline.core.jobs.apply_handler import SaveMeshMetadataHandler
from lightspeed.trex.asset_pipeline.core.jobs.asset_replace_apply_handler import AssetReplaceApplyHandler
from lightspeed.trex.asset_pipeline.core.jobs.asset_replace_apply_target import AssetReplaceApplyTarget
from lightspeed.trex.utils.common.prim_utils import is_mesh_asset
from omni.flux.job_queue.core.job import JobGraph
from pxr import Usd, UsdGeom, UsdShade


class ScaleMeshTestModifier(AssetModifierBase):
    """Scale geometry, optimize it, and replace the source reference. Skip a mesh without a bound material."""

    name = "test_scale_mesh"
    display_name = "Scale Mesh (Test)"
    tooltip = "Scale the selected meshes. Test only."
    experimental = True
    inputs = (
        ModifierInput("scale", "Scale", float, 1.0, tooltip="Multiply the mesh size.", min_value=0.1, max_value=10.0),
    )
    job_type = ScaleMeshTestJob

    def is_compatible(self, prim: Usd.Prim) -> bool:
        """Accept geometry meshes and Remix mesh asset rows."""
        return prim.IsA(UsdGeom.Mesh) or is_mesh_asset(prim)

    def build_graph(
        self, stage: Usd.Stage | None, graph: JobGraph, job: AssetModifierJob, target: AssetReplaceApplyTarget | None
    ) -> None:
        """Read the bound material into the job, then optimize the scaled mesh and replace the source reference."""
        if job.prim_paths:
            job.skip_reason = "The mesh has no bound material."
            for prim in Usd.PrimRange(stage.GetPrimAtPath(job.prim_paths[0])):
                material, _relationship = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
                if material:
                    job.values["material"] = str(material.GetPath())
                    job.skip_reason = None
                    break
        # A File Path Constant source has no reference to replace, so its processed model is only published.
        add_asset_optimization_jobs(
            graph,
            job.output(ScaleMeshTestJob.MESH_REQUEST),
            handler_type=AssetReplaceApplyHandler if target is not None else SaveMeshMetadataHandler,
            target=target,
        )
