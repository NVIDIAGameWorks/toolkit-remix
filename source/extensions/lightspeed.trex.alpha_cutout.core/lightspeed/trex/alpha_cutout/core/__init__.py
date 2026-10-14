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

__all__ = [
    "ALPHA_TEST_ALWAYS",
    "MATERIAL_PRIM_NAME",
    "REFERENCE_TARGET_PRIM_NAME",
    "REPLACEMENT_SUFFIX",
    "AlphaCutoutStageEditor",
    "ConversionTarget",
    "CutMesh",
    "CutoutParameters",
    "MeshCutoutResult",
    "MeshSource",
    "StageEditOutcome",
    "bend_normals_up",
    "convert_mesh",
    "convert_meshes",
    "cutout_file_name",
    "cutout_output_path",
    "cutout_root_prim_name",
    "find_capture_mesh_prim",
    "get_capture_mesh_root",
    "get_mesh_hash",
    "read_mesh_source",
    "read_mesh_sources",
    "read_replacement_mesh_source",
    "replacement_original_path",
    "replacement_output_path",
    "resolve_conversion_target",
    "resolve_conversion_targets",
    "simplify_ring_minimal",
    "smooth_normals",
    "thicken_mesh",
    "up_vector",
    "write_cutout_mesh",
    "write_cutout_replacement",
]

from .converter import convert_mesh, convert_meshes
from .data_models import (
    ConversionTarget,
    CutMesh,
    CutoutParameters,
    MeshCutoutResult,
    MeshSource,
    StageEditOutcome,
)
from .material_copy import ALPHA_TEST_ALWAYS
from .normals import bend_normals_up, smooth_normals, up_vector
from .simplify import simplify_ring_minimal
from .stage_edits import AlphaCutoutStageEditor
from .thicken import thicken_mesh
from .usd_reader import (
    REPLACEMENT_SUFFIX,
    find_capture_mesh_prim,
    get_capture_mesh_root,
    get_mesh_hash,
    read_mesh_source,
    read_mesh_sources,
    read_replacement_mesh_source,
    replacement_original_path,
    replacement_output_path,
    resolve_conversion_target,
    resolve_conversion_targets,
)
from .usd_writer import (
    MATERIAL_PRIM_NAME,
    REFERENCE_TARGET_PRIM_NAME,
    cutout_file_name,
    cutout_output_path,
    cutout_root_prim_name,
    write_cutout_mesh,
    write_cutout_replacement,
)
