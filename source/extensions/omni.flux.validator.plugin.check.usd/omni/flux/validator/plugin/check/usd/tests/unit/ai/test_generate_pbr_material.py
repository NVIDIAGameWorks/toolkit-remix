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

from unittest.mock import Mock

import omni.kit.commands
import omni.kit.test
from omni.flux.validator.plugin.check.usd.ai.generate_pbr_material import GeneratePBRMaterial


class TestGeneratePBRMaterial(omni.kit.test.AsyncTestCase):
    async def test_check_no_selector_data_should_skip_check(self):
        # Arrange
        generate_pbr = GeneratePBRMaterial()

        # Act
        success, message, data = await generate_pbr._check(Mock(), Mock(), [])

        # Assert
        self.assertTrue(success)
        self.assertEqual("Check:\n- SKIP: No selected prims", message)
        self.assertIsNone(data)
