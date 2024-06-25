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

import tempfile
from pathlib import Path

import carb
import omni.kit.test
from omni.flux.utils.material_converter.utils import MaterialConverterUtils
from omni.kit.test_suite.helpers import get_test_data_path


class TestUtils(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        self.temp_dir.cleanup()
        self.temp_dir = None

    async def test_get_material_library_shader_urls_should_return_library_paths(self):
        # Arrange
        # Make sure to test the token resolving
        lib_paths = (
            "${omni.flux.utils.material_converter}/data/tests/omni_core_materials/Base;"
            "${kit}/mdl/core/Base;${kit}/mdl/core/Volume;${kit}/mdl/core/mdl"
        )
        carb.settings.get_settings().set(MaterialConverterUtils.MATERIAL_LIBRARY_SETTING_PATH, lib_paths)

        # Act
        shaders = MaterialConverterUtils.get_material_library_shader_urls()

        # Assert
        for shader_url in shaders:
            self.assertTrue(shader_url.exists)

        self.assertTrue(
            # The lib path should point to the tests data mdl file
            Path(get_test_data_path(__name__, "omni_core_materials/Base/AperturePBR_Opacity.mdl")).resolve()
            in [Path(s.path).resolve() for s in shaders],
        )
