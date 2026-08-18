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

import pathlib

import omni.kit.test
from omni.flux.asset_importer.core.data_models import TextureTypes

from lightspeed.trex.asset_pipeline.core import RemixAssetPipelineConfig, build_remix_asset_pipeline


class TestPipelineBuilder(omni.kit.test.AsyncTestCase):
    async def test_build_remix_asset_pipeline_returns_canonical_order(self):
        """The canonical builder is the authoring point for step order."""
        # Arrange
        config = RemixAssetPipelineConfig(
            output_dir=pathlib.Path("/processed"),
            texture_type=TextureTypes.DIFFUSE,
        )

        # Act
        steps = build_remix_asset_pipeline(config)

        # Assert
        self.assertEqual(
            [step.name for step in steps],
            [
                "standardize_input",
                "triangulate_meshes",
                "convert_materials",
                "collect_textures",
                "convert_normal",
                "convert_dds",
                "update_textures",
                "write_metadata",
            ],
        )
