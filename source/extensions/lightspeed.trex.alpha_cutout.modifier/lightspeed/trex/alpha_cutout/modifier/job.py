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

__all__ = ["AlphaCardToMeshJob", "cutout_root_name", "output_file_name"]

import dataclasses
import pathlib
import re
from typing import Any, ClassVar

from lightspeed.common import constants
from lightspeed.trex.alpha_cutout.core import (
    MeshConversion,
    MeshSource,
    convert_mesh,
    parameters_from_values,
    read_mesh_source,
    write_cutout_file,
)
from lightspeed.trex.asset_modifiers.factory import AssetModifierJob
from lightspeed.trex.asset_pipeline.core.jobs.models import MeshOptimizationRequest
from lightspeed.trex.asset_pipeline.core.pipeline import MetaStepOperation
from lightspeed.trex.asset_pipeline.core.worker import run_in_worker_thread
from omni.flux.job_queue.core.job import JobInputs, JobOutputPort, JobOutputs, JobProgress, JobProgressCallback
from pxr import Usd

from .report import ConversionReport, MeshReport
from .values import MATERIAL_KEY, MATERIAL_PRIM_KEY, MESHES_KEY, PRIM_PATH_KEY, TEXTURE_KEY

_OUTPUT_PREFIX = "cutout_"
_CAPTURE_MESH_PREFIX = "mesh_"
_OUTPUT_SUFFIX = ".usda"


def output_file_name(source_url: str) -> str:
    """Name the cutout after its source model so the published file reads as such in the Selection panel.

    Args:
        source_url: Path of the model file.

    Returns:
        ``cutout_<HASH>.usda`` for a capture mesh file, ``cutout_<name>.usda`` otherwise.
    """
    stem = pathlib.PurePath(source_url).stem
    return f"{_OUTPUT_PREFIX}{stem.removeprefix(_CAPTURE_MESH_PREFIX)}{_OUTPUT_SUFFIX}"


def cutout_root_name(stage: Usd.Stage, output_stem: str) -> str | None:
    """Name the root prim of a capture mesh cutout after the output file.

    The toolkit maps a prim of a mesh asset to its instances by the last prim in its path that is named like a
    capture mesh. A cutout that kept the capture root name would map to a path that does not exist, so its prims
    could not be selected.

    Args:
        stage: Model stage.
        output_stem: Stem of the output file.

    Returns:
        The output stem for a capture mesh file, ``None`` when the model keeps its root name.
    """
    root = stage.GetDefaultPrim()
    if root and root.IsValid() and re.match(constants.REGEX_MESH_PATH, root.GetName()):
        return output_stem
    return None


def _open_model(source_url: str) -> Usd.Stage:
    """Open the model file.

    Args:
        source_url: Path of the model file.

    Returns:
        The opened stage.

    Raises:
        RuntimeError: If the model file cannot be opened.
    """
    stage = Usd.Stage.Open(source_url)
    if not stage:
        raise RuntimeError(f"The model file {source_url} could not be opened.")
    return stage


def _read_sources(stage: Usd.Stage, entries: list[dict[str, Any]]) -> list[MeshSource]:
    """Read every listed mesh from the model stage.

    Args:
        stage: Stage of the model file.
        entries: Mesh entries stored by ``build_graph``.

    Returns:
        One source per entry, in order.
    """
    return [read_mesh_source(stage, entry[PRIM_PATH_KEY], entry[TEXTURE_KEY]) for entry in entries]


@dataclasses.dataclass
class AlphaCardToMeshJob(AssetModifierJob):
    """Cut the listed meshes of one model file and hand the unoptimized model to mesh optimization."""

    MESH_REQUEST: ClassVar[JobOutputPort[MeshOptimizationRequest]] = JobOutputPort(
        "mesh_request", MeshOptimizationRequest
    )
    REPORT: ClassVar[JobOutputPort[ConversionReport]] = JobOutputPort("report", ConversionReport)
    output_ports: ClassVar[tuple[JobOutputPort[Any], ...]] = (MESH_REQUEST, REPORT)

    async def execute(
        self, job_directory: pathlib.Path, inputs: JobInputs, progress_callback: JobProgressCallback
    ) -> JobOutputs:
        """Write ``cutout.usda`` with the cut meshes, absolute texture paths and bare MDL module names.

        Each mesh is cut on a worker thread and progress is reported in between, which is also where a
        cancellation lands. A mesh that yields no geometry is copied unchanged; the job is skipped only when no
        mesh converted.

        Args:
            job_directory: Scratch folder of this job.
            inputs: Unused; the job has no input ports.
            progress_callback: Receives one update per mesh.

        Returns:
            The mesh optimization request on ``MESH_REQUEST`` and the geometry counts on ``REPORT``.
        """
        parameters = parameters_from_values(self.values)
        entries = list(self.values.get(MESHES_KEY, ()))
        stage = await run_in_worker_thread(_open_model, self.source_url)
        sources = await run_in_worker_thread(_read_sources, stage, entries)
        conversions: list[MeshConversion] = []
        reports: list[MeshReport] = []
        skipped: list[str] = []
        total = len(entries)
        for index, (entry, source) in enumerate(zip(entries, sources, strict=True)):
            name = entry[PRIM_PATH_KEY].rsplit("/", 1)[-1]
            await progress_callback(JobProgress(completed=index, total=total, detail=f"Cutting {name}"))
            try:
                result = await run_in_worker_thread(convert_mesh, source, parameters)
            except (OSError, ValueError) as error:
                skipped.append(f"{name}: {error}")
                reports.append(MeshReport.from_conversion(entry[PRIM_PATH_KEY], source, None, str(error)))
                continue
            if result is None or result.cut_mesh is None:
                reason = result.skip_reason if result else "cancelled"
                skipped.append(f"{name}: {reason}")
                reports.append(MeshReport.from_conversion(entry[PRIM_PATH_KEY], source, None, reason))
                continue
            reports.append(MeshReport.from_conversion(entry[PRIM_PATH_KEY], source, result.cut_mesh))
            conversions.append(
                MeshConversion(
                    entry[PRIM_PATH_KEY], result.cut_mesh, entry.get(MATERIAL_KEY), entry.get(MATERIAL_PRIM_KEY)
                )
            )
        output = job_directory / output_file_name(self.source_url)
        await run_in_worker_thread(
            write_cutout_file,
            self.source_url,
            output,
            conversions,
            parameters.disable_alpha_test,
            cutout_root_name(stage, output.stem),
        )
        await progress_callback(JobProgress(completed=total, total=total, detail="Cutout written"))
        outputs = {
            # The cutout replaces its source in place, so its geometry keeps the scale of the source.
            self.MESH_REQUEST: MeshOptimizationRequest(
                output,
                job_directory,
                self.output_url,
                skip_operations=(MetaStepOperation.SCALE_NORMALIZATION,),
            ),
            self.REPORT: ConversionReport(tuple(reports)),
        }
        if not conversions:
            return JobOutputs(outputs, skip_reason="No mesh was converted. " + "; ".join(skipped))
        return JobOutputs(outputs)
