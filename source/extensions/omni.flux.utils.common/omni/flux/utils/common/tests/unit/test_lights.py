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

import omni.kit.test
from omni.flux.utils.common import lights as _lights


class TestLights(omni.kit.test.AsyncTestCase):
    async def test_get_light_type_returns_expected_enum_for_known_light_class(self):
        # Arrange

        # Act
        result = _lights.get_light_type("RectLight")

        # Assert
        self.assertEqual(_lights.LightTypes.RectLight, result)
        self.assertEqual("Rect Light", result.value)

    async def test_get_light_type_returns_dome_light_for_dome_light_alias(self):
        # Arrange

        # Act
        result = _lights.get_light_type("DomeLight_1")

        # Assert
        self.assertEqual(_lights.LightTypes.DomeLight, result)

    async def test_get_light_type_returns_none_for_unknown_light_class(self):
        # Arrange

        # Act
        result = _lights.get_light_type("UnknownLight")

        # Assert
        self.assertIsNone(result)
