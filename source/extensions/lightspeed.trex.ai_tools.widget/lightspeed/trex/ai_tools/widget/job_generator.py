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

import copy
import dataclasses
import pathlib
from collections.abc import Callable, Iterator

import carb
from lightspeed.trex.utils.common import prim_utils
import omni.flux.job_queue.core.interface
import omni.flux.job_queue.core.job
import omni.usd
from lightspeed.trex.ai_tools.widget.comfy import Workflow
from lightspeed.trex.ai_tools.widget.job import ComfyJob
from lightspeed.trex.ai_tools.widget.settings import get_comfy_url
from lightspeed.trex.asset_replacements.core.shared import Setup as AssetReplacementCore
from lightspeed.trex.utils.common.prim_utils import is_shader_prototype
from omni.flux.asset_importer.core.data_models import TextureTypes
from pxr import Usd, UsdShade


def iter_selected_prims(context_name: str = "") -> Iterator[Usd.Prim]:
    """
    Iterate over currently selected prims in the USD stage.

    Args:
        context_name: The USD context name. Empty string uses the default context.

    Yields:
        Selected prims that exist in the stage.

    Raises:
        RuntimeError: If no USD stage is loaded.
    """
    context = omni.usd.get_context(context_name)
    stage = context.get_stage()
    if stage is None:
        raise RuntimeError("No USD stage is loaded.")

    for prim_path in context.get_selection().get_selected_prim_paths():
        prim = stage.GetPrimAtPath(prim_path)
        if prim:
            yield prim


def iter_related_prims(prim: Usd.Prim, _visited: set[str] | None = None) -> Iterator[Usd.Prim]:
    """
    Iterate over prims related to the given prim.

    Traverses the hierarchy to find related prims, following RTX Remix conventions:
    - Children of the prim
    - Prototypes (resolved from instances via get_prototype)
    - Materials (from mesh bindings)
    - Shaders (from materials)

    This is used to find the shader prim for applying texture changes
    when the user selects an instance, mesh, or material.

    Args:
        prim: The starting prim.

    Yields:
        The prim itself and all related prims.
    """
    if _visited is None:
        _visited = set()

    prim_path = str(prim.GetPath())
    if prim_path in _visited:
        return

    _visited.add(prim_path)
    yield prim

    # Process children
    for child in prim_utils.get_children_prims(prim):
        yield from iter_related_prims(child, _visited)

    # Handle instance -> prototype conversion
    prototype = prim_utils.get_prototype(prim)
    if prototype and prototype != prim:
        yield from iter_related_prims(prototype, _visited)

    # Handle mesh -> material conversion
    elif prim_utils.is_mesh_prototype(prim):
        material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        if material:
            yield from iter_related_prims(material.GetPrim(), _visited)

    # Handle material -> shader conversion
    elif prim_utils.is_material_prototype(prim):
        shader = omni.usd.get_shader_from_material(prim, True)
        if shader:
            yield from iter_related_prims(shader, _visited)


def iter_texture_path(prim: Usd.Prim, texture_type: TextureTypes = TextureTypes.DIFFUSE) -> Iterator[pathlib.Path]:
    """
    Iterate over texture paths for a given prim and texture type.

    Traverses related prims to find shader prototypes, then extracts
    texture paths for the specified texture type.

    Args:
        prim: The prim to find textures for.
        texture_type: The type of texture to find (default: DIFFUSE).

    Yields:
        Paths to texture files.
    """
    for related_prim in iter_related_prims(prim):
        if is_shader_prototype(related_prim):
            textures = AssetReplacementCore("").get_textures_from_material_path(
                str(related_prim.GetPath()), {texture_type}
            )
            for _, path in textures:
                yield path


@dataclasses.dataclass
class ComfyJobGenerator:
    """
    Generates and submits ComfyUI jobs based on selected prims.

    Prims are grouped by unique input data paths (resolved from LazyValues) to
    avoid duplicate work - if multiple prims share the same input files, only
    one job is created and the results are applied to all prims in the group.

    Jobs are named after the input file (not the prim path). When results
    are applied, ComfyJobApplyHandler processes the job's OutputArtifacts
    and delegates to specialized handlers (TextureArtifactHandler, etc.).
    """

    producer: Callable[[], Iterator[Usd.Prim]]
    comfy_url: str = dataclasses.field(default_factory=get_comfy_url)
    context_name: str = ""

    def submit(
        self,
        interface: omni.flux.job_queue.core.interface.QueueInterface,
        workflow: Workflow,
        use_inputs_for_output_filename_prefix: bool = False,
    ) -> None:
        """Submit jobs for all prims returned by the producer, grouped by unique input data paths."""
        graph = omni.flux.job_queue.core.job.JobGraph(
            name=workflow.name,
            interface=interface,
        )

        # Group prims by resolved input data paths to avoid duplicate work
        # Key: input data paths (or prim_path as fallback), Value: (prim_paths, workflow)
        input_data_to_prims: dict[str, tuple[list[str], Workflow]] = {}

        for prim in self.producer():
            prim_path = str(prim.GetPath())

            job_workflow = copy.deepcopy(workflow)

            # Evaluate lazy values for this prim and collect file paths as group key
            input_data_key_parts: list[str] = []

            for field in job_workflow.inputs:
                if callable(field.value):
                    new_value = field.value(prim)
                    if isinstance(new_value, pathlib.Path):
                        input_data_key_parts.append(str(new_value))
                    field.value = new_value

            # Use the input data path(s) as a grouping key
            # If no file paths found, use prim_path as fallback key
            input_data_key = "|".join(sorted(input_data_key_parts)) if input_data_key_parts else prim_path

            if input_data_key in input_data_to_prims:
                # Add this prim to the existing group
                input_data_to_prims[input_data_key][0].append(prim_path)
            else:
                # Create a new group
                input_data_to_prims[input_data_key] = ([prim_path], job_workflow)

        # Create one job per unique input data group
        for input_data_key, (prim_paths, job_workflow) in input_data_to_prims.items():
            # Use the first file path stem as job name, or fall back to first prim path
            key_parts = input_data_key.split("|")
            if key_parts and key_parts[0] and key_parts[0] != prim_paths[0]:
                job_name = pathlib.Path(key_parts[0]).stem
            else:
                job_name = prim_paths[0]

            # Determine output_filename_prefix: only use if there's exactly one file path input for this job
            if use_inputs_for_output_filename_prefix and len(key_parts) == 1 and key_parts[0] != prim_paths[0]:
                output_filename_prefix = pathlib.Path(key_parts[0]).stem
            else:
                output_filename_prefix = None

            job = ComfyJob(
                name=job_name,
                prim_paths=prim_paths,
                comfy_url=self.comfy_url,
                workflow=job_workflow,
                output_filename_prefix=output_filename_prefix,
            )

            graph.add_job(job)

        if not graph.jobs:
            carb.log_warn("[ComfyJobGenerator] No jobs to submit.")
            return

        graph.submit()
