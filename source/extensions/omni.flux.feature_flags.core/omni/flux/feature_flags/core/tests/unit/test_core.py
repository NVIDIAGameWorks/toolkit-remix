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

import carb
from omni.flux.feature_flags.core import FeatureFlagsCore
from omni.kit.test.async_unittest import AsyncTestCase


class TestFeatureFlagsCore(AsyncTestCase):
    async def setUp(self):
        self.core = FeatureFlagsCore()
        self.persistent_path = FeatureFlagsCore._PERSISTENT_PREFIX  # noqa PLW0212
        self.settings_path = FeatureFlagsCore._FEATURE_FLAGS_SETTING  # noqa PLW0212

        self.settings = carb.settings.get_settings()

    # After running each test
    async def tearDown(self):
        # Cleanup the Feature Flag settings
        self.settings.destroy_item(self.settings_path)
        self.settings.destroy_item(self.persistent_path + self.settings_path)

        self.core = None
        self.persistent_path = None
        self.settings_path = None

        self.settings = None

    async def test_get_all_flags_returns_all_settings_feature_flags(self):
        # Arrange
        value = True
        display_name = "Test Feature Flag"
        tooltip = "Tooltip for Test Feature Flag"

        # test_01 Feature Flag
        self.settings.set(f"{self.settings_path}/test_01/value", value)
        self.settings.set(f"{self.settings_path}/test_01/display_name", display_name)
        self.settings.set(f"{self.settings_path}/test_01/tooltip", tooltip)

        # test_02 Feature Flag
        self.settings.set(f"{self.settings_path}/test_02/value", value)
        self.settings.set(f"{self.settings_path}/test_02/tooltip", tooltip)

        # test_02 Feature Flag
        self.settings.set(f"{self.settings_path}/test_03/value", value)
        self.settings.set(f"{self.settings_path}/test_03/display_name", display_name)

        # test_03 Feature Flag
        self.settings.set(f"{self.settings_path}/test_04/value", value)

        # Act
        flags = self.core.get_all_flags()

        # Assert
        self.assertEqual(len(flags), 4)

        self.assertEqual(flags[0].key, "test_01")
        self.assertEqual(flags[1].key, "test_02")
        self.assertEqual(flags[2].key, "test_03")
        self.assertEqual(flags[3].key, "test_04")

    async def test_get_all_flags_should_cleanup_persistent_settings(self):
        # Arrange
        self.settings.set(f"{self.settings_path}/test_transient/value", True)
        self.settings.set(f"{self.settings_path}/test_both/value", True)
        self.settings.set(f"{self.persistent_path}{self.settings_path}/test_both/value", False)
        self.settings.set(f"{self.persistent_path}{self.settings_path}/test_persistent/value", True)

        # Act
        flags = self.core.get_all_flags()

        # Assert
        self.assertEqual(len(flags), 2)
        self.assertEqual(flags[0].key, "test_transient")
        self.assertEqual(flags[1].key, "test_both")

    async def test_get_all_flags_should_update_value_using_persistent_settings(self):
        # Arrange
        display_name = "Test Feature Flag"
        tooltip = "Tooltip for Test Feature Flag"

        self.settings.set(f"{self.settings_path}/test_value/value", True)
        self.settings.set(f"{self.settings_path}/test_value/display_name", display_name)
        self.settings.set(f"{self.settings_path}/test_value/tooltip", tooltip)

        self.settings.set(f"{self.persistent_path}{self.settings_path}/test_value/value", False)

        # Act
        flags = self.core.get_all_flags()

        # Assert
        self.assertEqual(len(flags), 1)

        self.assertEqual(flags[0].value, False)
        self.assertEqual(flags[0].display_name, display_name)
        self.assertEqual(flags[0].tooltip, tooltip)

    async def test_get_flag_should_return_flag_with_key(self):
        # Arrange
        self.settings.set(f"{self.settings_path}/test_value/value", True)

        # Act
        flag = self.core.get_flag("test_value")

        # Assert
        self.assertEqual(flag.key, "test_value")

    async def test_get_flag_doesnt_exist_should_raise_value_error(self):
        # Arrange
        self.settings.set(f"{self.settings_path}/test_value/value", True)

        with self.assertRaises(ValueError) as cm:
            # Act
            self.core.get_flag("flag_doesnt_exist")

        # Assert
        self.assertEqual(str(cm.exception), "Feature flag 'flag_doesnt_exist' not found.")

    async def test_set_enabled_should_set_feature_flag_persistent_value(self):
        # Arrange
        display_name = "Test Feature Flag"
        tooltip = "Tooltip for Test Feature Flag"

        self.settings.set(f"{self.settings_path}/test_value/value", True)
        self.settings.set(f"{self.settings_path}/test_value/display_name", display_name)
        self.settings.set(f"{self.settings_path}/test_value/tooltip", tooltip)

        # Act
        self.core.set_enabled("test_value", False)

        # Assert
        persistent_value = self.settings.get(f"{self.persistent_path}{self.settings_path}/test_value/value")
        self.assertEqual(persistent_value, False)

    async def test_set_enabled_all_should_set_all_feature_flags_persistent_values(self):
        # Arrange
        display_name = "Test Feature Flag"
        tooltip = "Tooltip for Test Feature Flag"

        self.settings.set(f"{self.settings_path}/test_01/value", True)
        self.settings.set(f"{self.settings_path}/test_01/display_name", display_name)
        self.settings.set(f"{self.settings_path}/test_01/tooltip", tooltip)

        self.settings.set(f"{self.settings_path}/test_02/value", True)
        self.settings.set(f"{self.settings_path}/test_02/display_name", display_name)
        self.settings.set(f"{self.settings_path}/test_02/tooltip", tooltip)

        self.settings.set(f"{self.settings_path}/test_03/value", True)
        self.settings.set(f"{self.settings_path}/test_03/display_name", display_name)
        self.settings.set(f"{self.settings_path}/test_03/tooltip", tooltip)

        # Act
        self.core.set_enabled_all(False)

        # Assert
        for flag in ["test_01", "test_02", "test_03"]:
            persistent_value = self.settings.get(f"{self.persistent_path}{self.settings_path}/{flag}/value")
            self.assertEqual(persistent_value, False)

    async def test_is_enabled_should_return_flag_value(self):
        # Arrange
        self.settings.set(f"{self.settings_path}/test_value/value", True)

        # Act
        enabled = self.core.is_enabled("test_value")

        # Assert
        self.assertEqual(enabled, True)

    async def test_is_enabled_doesnt_exist_should_raise_value_error(self):
        # Arrange
        self.settings.set(f"{self.settings_path}/test_value/value", True)

        with self.assertRaises(ValueError) as cm:
            # Act
            self.core.is_enabled("flag_doesnt_exist")

        # Assert
        self.assertEqual(str(cm.exception), "Feature flag 'flag_doesnt_exist' not found.")

    async def test_subscribe_feature_flags_changed_should_trigger_callback_on_feature_flag_changed(self):
        for use_persistent in [True, False]:
            with self.subTest(title=f"use_persistent_{use_persistent}"):
                # Arrange
                self.settings.set(f"{self.settings_path}/test_value/value", True)
                callback_mock = Mock()

                _ = self.core.subscribe_feature_flags_changed(callback_mock)

                # Act
                self.settings.set(
                    f"{self.persistent_path if use_persistent else ''}{self.settings_path}/test_value/value", False
                )

                # Assert
                self.assertEqual(callback_mock.call_count, 2 if use_persistent else 1)
