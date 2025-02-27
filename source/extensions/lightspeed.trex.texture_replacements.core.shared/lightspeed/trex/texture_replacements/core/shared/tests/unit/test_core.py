"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import omni.usd
from lightspeed.trex.texture_replacements.core.shared import TextureReplacementsCore
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage


class TestTextureReplacementsCore(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await open_stage(_get_test_data("usd/project_example/combined.usda"))
        self.context = omni.usd.get_context()

    # After running each test
    async def tearDown(self):
        if self.context.get_stage():
            await self.context.close_stage_async()

    async def test_get_expected_texture_material_inputs(self):
        # Arrange
        core = TextureReplacementsCore(self.context.get_name())

        # Act
        shader_inputs = await core.get_expected_texture_material_inputs("/RootNode/Looks/mat_BC868CE5A075ABB1/Shader")

        # Assert
        expected_attributes = [
            "diffuse_texture",
            "metallic_texture",
            "normalmap_texture",
            "reflectionroughness_texture",
        ]
        # ex: "
        input_names = [shader_input.split(":")[1] for shader_input in shader_inputs]
        self.assertTrue(shader_inputs)
        self.assertEqual(input_names, expected_attributes)
