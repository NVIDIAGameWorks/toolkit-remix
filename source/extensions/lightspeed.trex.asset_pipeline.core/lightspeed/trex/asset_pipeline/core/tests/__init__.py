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

from .unit.test_asset_processing_job import TestTextureProcessingJob
from .unit.test_asset_processing_models import TestTextureProcessingModels
from .e2e.test_asset_processing_job import TestTextureProcessingJobE2E
from .e2e.test_publication import TestAssetPublicationE2E
from .unit.test_collect_textures import TestCollectTextures
from .unit.test_convert_dds import TestConvertDDS
from .unit.test_convert_materials import TestConvertMaterials
from .unit.test_convert_normal import TestConvertNormal
from .unit.test_pipeline_builder import TestPipelineBuilder
from .unit.test_pipeline_context import TestRemixAssetPipelineContext
from .unit.test_pipeline_runner import TestRemixAssetPipelineRunner
from .unit.test_standardize_input import TestStandardizeInput
from .unit.test_triangulate_meshes import TestTriangulateMeshes
from .unit.test_write_metadata import TestWriteMetadata
from .e2e.test_collect_textures import TestCollectTexturesE2E
from .e2e.test_convert_materials import TestConvertMaterialsE2E
from .e2e.test_pipeline import TestRemixAssetPipelineE2E
from .e2e.test_triangulate_meshes import TestTriangulateMeshesE2E
from .e2e.test_update_textures import TestUpdateTexturesE2E

__all__ = (
    "TestAssetPublicationE2E",
    "TestCollectTextures",
    "TestCollectTexturesE2E",
    "TestConvertDDS",
    "TestConvertMaterials",
    "TestConvertMaterialsE2E",
    "TestConvertNormal",
    "TestPipelineBuilder",
    "TestRemixAssetPipelineContext",
    "TestRemixAssetPipelineE2E",
    "TestRemixAssetPipelineRunner",
    "TestStandardizeInput",
    "TestTextureProcessingJob",
    "TestTextureProcessingJobE2E",
    "TestTextureProcessingModels",
    "TestTriangulateMeshes",
    "TestTriangulateMeshesE2E",
    "TestUpdateTexturesE2E",
    "TestWriteMetadata",
)
