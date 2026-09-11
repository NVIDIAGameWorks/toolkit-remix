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

from .e2e.test_apply_processed_textures import TestApplyProcessedTexturesE2E
from .e2e.test_context import TestRemixAssetPipelineContextE2E
from .e2e.test_convert_materials import TestConvertMaterialsE2E
from .e2e.test_discover_textures import TestDiscoverTexturesE2E
from .e2e.test_job import TestMeshOptimizationGraphE2E, TestTextureProcessingJobE2E
from .e2e.test_legacy_fixtures import TestLegacyFixtureParityE2E
from .e2e.test_material_cleanup import TestMaterialCleanupE2E
from .e2e.test_meta import TestMetaE2E
from .e2e.test_normalize_emissive_intensity import TestNormalizeEmissiveIntensityE2E
from .e2e.test_utils import TestAssetPublicationE2E
from .e2e.test_reference import TestReferenceE2E
from .e2e.test_runner import TestPipelineRunnerE2E
from .unit.test_apply_handler import TestApplyHandler
from .unit.test_builder import TestPipelineBuilder
from .unit.test_codecs import TestCodecAssemblies
from .unit.test_context import TestRemixAssetPipelineContext
from .unit.test_convert_dds import TestConvertDDS
from .unit.test_convert_materials import TestConvertMaterials
from .unit.test_convert_normal import TestConvertNormal
from .unit.test_graphs import TestGraphFactories
from .unit.test_mesh_optimization import TestMeshOptimizationJob
from .unit.test_metadata import TestMetadataUtilities
from .unit.test_models import (
    TestMeshOptimizationRequest,
    TestMeshOptimizationResult,
    TestPrepareOptimizationResult,
    TestResolveProcessedTextures,
    TestTextureProcessingItem,
    TestTextureProcessingRequest,
    TestTextureProcessingResult,
)
from .unit.test_runner import TestRemixAssetPipelineRunner
from .unit.test_standardize_input import TestStandardizeInput

__all__ = (
    "TestApplyHandler",
    "TestApplyProcessedTexturesE2E",
    "TestAssetPublicationE2E",
    "TestCodecAssemblies",
    "TestConvertDDS",
    "TestConvertMaterials",
    "TestConvertMaterialsE2E",
    "TestConvertNormal",
    "TestDiscoverTexturesE2E",
    "TestGraphFactories",
    "TestLegacyFixtureParityE2E",
    "TestMaterialCleanupE2E",
    "TestMeshOptimizationGraphE2E",
    "TestMeshOptimizationJob",
    "TestMeshOptimizationRequest",
    "TestMeshOptimizationResult",
    "TestMetaE2E",
    "TestMetadataUtilities",
    "TestNormalizeEmissiveIntensityE2E",
    "TestPipelineBuilder",
    "TestPipelineRunnerE2E",
    "TestPrepareOptimizationResult",
    "TestReferenceE2E",
    "TestRemixAssetPipelineContext",
    "TestRemixAssetPipelineContextE2E",
    "TestRemixAssetPipelineRunner",
    "TestResolveProcessedTextures",
    "TestStandardizeInput",
    "TestTextureProcessingItem",
    "TestTextureProcessingJobE2E",
    "TestTextureProcessingRequest",
    "TestTextureProcessingResult",
)
