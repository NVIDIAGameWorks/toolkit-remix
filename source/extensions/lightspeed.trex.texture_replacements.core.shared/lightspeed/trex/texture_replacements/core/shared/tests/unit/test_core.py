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

from unittest.mock import Mock, call, patch

import omni.usd
from lightspeed.trex.texture_replacements.core.shared import TextureReplacementsCore
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP, TextureTypes
from omni.flux.material_api import ShaderInfoAPI
from omni.flux.utils.widget.resources import get_test_data
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage
from pxr import Sdf


class TestTextureReplacementsCore(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await open_stage(get_test_data("usd/project_example/combined.usda"))
        self.context = omni.usd.get_context()

    # After running each test
    async def tearDown(self):
        if self.context.get_stage():
            await self.context.close_stage_async()

    async def test_get_expected_texture_material_inputs(self):
        for test_data in [
            (None, list(set(TEXTURE_TYPE_INPUT_MAP.values()))),
            (TextureTypes.DIFFUSE, ["inputs:diffuse_texture"]),
        ]:
            texture_type, expected_attributes = test_data
            expected_attributes.sort()

            with self.subTest(name=f"texture_type_{texture_type}"):
                # Arrange
                core = TextureReplacementsCore(self.context.get_name())

                prim_path = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader"
                expected_prim = self.context.get_stage().GetPrimAtPath(Sdf.Path(prim_path).GetPrimPath())

                with (
                    patch.object(ShaderInfoAPI, "__init__") as mock_shader_info_api,
                    patch.object(ShaderInfoAPI, "get_input_properties") as mock_get_input_properties,
                ):
                    mock_shader_info_api.return_value = None

                    input_properties = []
                    for input_property in TEXTURE_TYPE_INPUT_MAP.values():
                        property_mock = Mock()
                        property_mock.GetName.return_value = input_property
                        input_properties.append(property_mock)
                    mock_get_input_properties.return_value = input_properties

                    # Act
                    shader_inputs = await core.get_expected_texture_material_inputs(
                        prim_path, texture_type=texture_type
                    )

                # Assert
                self.assertEqual(mock_shader_info_api.call_count, 1)
                self.assertEqual(mock_shader_info_api.call_args, call(expected_prim))

                input_names = sorted([shader_input.split(".")[-1] for shader_input in shader_inputs])
                self.assertTrue(shader_inputs)
                self.assertEqual(input_names, expected_attributes)
