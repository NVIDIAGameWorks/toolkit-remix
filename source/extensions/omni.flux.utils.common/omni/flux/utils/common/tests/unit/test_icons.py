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

from unittest.mock import Mock, patch

import omni.kit.test
from omni.flux.utils.common import icons as _icons


class TestIcons(omni.kit.test.AsyncTestCase):
    async def test_get_prim_type_icons_returns_copy_when_settings_value_is_dict(self):
        # Arrange
        settings = Mock()
        settings.get.return_value = {"Mesh": "MeshIcon"}

        with patch.object(_icons.carb.settings, "get_settings", return_value=settings):
            # Act
            result = _icons.get_prim_type_icons()

        # Assert
        self.assertEqual({"Mesh": "MeshIcon"}, result)
        self.assertIsNot(settings.get.return_value, result)
        settings.get.assert_called_once_with(_icons.ICONS_SETTING_PATH)

    async def test_get_prim_type_icons_returns_empty_dict_when_settings_value_is_not_dict(self):
        # Arrange
        settings = Mock()
        settings.get.return_value = ["Mesh", "MeshIcon"]

        with patch.object(_icons.carb.settings, "get_settings", return_value=settings):
            # Act
            result = _icons.get_prim_type_icons()

        # Assert
        self.assertEqual({}, result)
        settings.get.assert_called_once_with(_icons.ICONS_SETTING_PATH)
