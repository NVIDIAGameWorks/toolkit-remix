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

from .e2e.test_stage_edits_workflow import TestAlphaCutoutStageEditsE2E
from .unit.test_converter import TestConvertMeshes
from .unit.test_cut import TestCutTriangles
from .unit.test_mask import TestMask
from .unit.test_normals import TestNormals
from .unit.test_material_copy import TestCopyMaterialFlattened
from .unit.test_simplify import TestSimplifyRingMinimal
from .unit.test_stage_edits import TestAlphaCutoutStageEditor
from .unit.test_thicken import TestThickenMesh
from .unit.test_triangulate import TestEarclip
from .unit.test_usd_reader import TestReadMeshSource
from .unit.test_usd_writer import TestWriteCutoutMesh

__all__ = [
    "TestAlphaCutoutStageEditor",
    "TestAlphaCutoutStageEditsE2E",
    "TestConvertMeshes",
    "TestCopyMaterialFlattened",
    "TestCutTriangles",
    "TestEarclip",
    "TestMask",
    "TestNormals",
    "TestReadMeshSource",
    "TestSimplifyRingMinimal",
    "TestThickenMesh",
    "TestWriteCutoutMesh",
]
