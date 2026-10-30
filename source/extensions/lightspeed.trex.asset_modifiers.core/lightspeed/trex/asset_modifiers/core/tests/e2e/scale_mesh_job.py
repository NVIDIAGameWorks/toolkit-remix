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

__all__ = ["ScaleMeshTestJob"]

import dataclasses
import pathlib
from typing import Any, ClassVar

from lightspeed.trex.asset_modifiers.factory import AssetModifierJob
from lightspeed.trex.asset_pipeline.core.jobs.models import MeshOptimizationRequest
from lightspeed.trex.asset_pipeline.core.worker import run_in_worker_thread
from omni.flux.job_queue.core.job import JobInputs, JobOutputPort, JobOutputs, JobProgress, JobProgressCallback
from omni.flux.utils.common.path_utils import get_absolute_path_from_relative
from pxr import Usd, UsdGeom, UsdUtils


@dataclasses.dataclass
class ScaleMeshTestJob(AssetModifierJob):
    """Scale real mesh points and hand the unoptimized model to mesh optimization."""

    MESH_REQUEST: ClassVar[JobOutputPort[MeshOptimizationRequest]] = JobOutputPort(
        "mesh_request", MeshOptimizationRequest
    )
    output_ports: ClassVar[tuple[JobOutputPort[Any], ...]] = (MESH_REQUEST,)

    async def execute(
        self, job_directory: pathlib.Path, inputs: JobInputs, progress_callback: JobProgressCallback
    ) -> JobOutputs:
        """Write scaled.usda with absolute paths for external textures and sub-USD files."""
        output = await run_in_worker_thread(
            self._scale_source, self.source_url, job_directory / "scaled.usda", self.values["scale"]
        )
        await progress_callback(JobProgress(completed=1, total=1, detail="Scale mesh"))
        return JobOutputs({self.MESH_REQUEST: MeshOptimizationRequest(output, job_directory, self.output_url)})

    @staticmethod
    def _scale_source(source_url: str, destination: pathlib.Path, scale: float) -> pathlib.Path:
        """Scale mesh points and export absolute file paths without changing MDL module names."""
        stage = Usd.Stage.Open(source_url)
        source_layer = stage.GetRootLayer()
        flattened = stage.Flatten()
        UsdUtils.ModifyAssetPaths(
            flattened,
            lambda path: (
                path
                if not path or pathlib.PurePosixPath(path).suffix.lower() == ".mdl"
                else get_absolute_path_from_relative(path, source_layer)
            ),
        )
        output_stage = Usd.Stage.Open(flattened)
        for prim in output_stage.Traverse():
            if prim.IsA(UsdGeom.Mesh):
                points = UsdGeom.Mesh(prim).GetPointsAttr()
                for time in (Usd.TimeCode.Default(), *points.GetTimeSamples()):
                    points.Set([point * scale for point in points.Get(time)], time)
        flattened.Export(str(destination))
        return destination
