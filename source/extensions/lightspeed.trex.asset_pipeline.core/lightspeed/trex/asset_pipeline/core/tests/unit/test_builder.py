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

from lightspeed.trex.asset_pipeline.core import RemixAssetPipelineConfig, build_remix_mesh_pipeline


class TestPipelineBuilder(omni.kit.test.AsyncTestCase):
    """Test the pipeline phase builders return the approved step order."""

    def test_build_remix_mesh_pipeline_returns_mesh_order(self):
        """The mesh phase runs import, cleanup, conversion, application, reference, and meta."""
        # Act
        steps = build_remix_mesh_pipeline(
            RemixAssetPipelineConfig(output_dir=pathlib.Path("/processed"), texture_type=None),
            {},
        )
        # Assert
        self.assertEqual(
            [step.name for step in steps],
            [
                "standardize_input",
                "material_cleanup",
                "convert_materials",
                "normalize_emissive_intensity",
                "apply_processed_textures",
                "reference",
                "meta",
            ],
        )
