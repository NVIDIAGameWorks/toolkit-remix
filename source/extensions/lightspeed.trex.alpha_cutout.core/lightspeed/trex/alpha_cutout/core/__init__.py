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
    "MATERIAL_PRIM_ATTR",
    "MATERIAL_PRIM_NAME",
    "SOURCE_FILE_ATTR",
    "SOURCE_PRIM_ATTR",
    "CutMesh",
    "CutoutParameters",
    "MeshConversion",
    "MeshCutoutResult",
    "MeshSource",
    "convert_mesh",
    "get_bound_material",
    "get_diffuse_texture_path",
    "is_convertible_mesh",
    "parameters_from_values",
    "read_mesh_source",
    "read_origin",
    "snapshot_material",
    "write_cutout_file",
]

from .converter import convert_mesh, parameters_from_values
from .cutout_file import (
    MATERIAL_PRIM_ATTR,
    MATERIAL_PRIM_NAME,
    SOURCE_FILE_ATTR,
    SOURCE_PRIM_ATTR,
    MeshConversion,
    read_origin,
    write_cutout_file,
)
from .data_models import CutMesh, CutoutParameters, MeshCutoutResult, MeshSource
from .material_snapshot import ALPHA_TEST_ALWAYS, snapshot_material
from .usd_reader import get_bound_material, get_diffuse_texture_path, is_convertible_mesh, read_mesh_source
