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
from omni.flux.feature_flags.window import get_instance
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


class TestFeatureFlagsWindow(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()

        self.persistent_path = FeatureFlagsCore._PERSISTENT_PREFIX
        self.settings_path = FeatureFlagsCore._FEATURE_FLAGS_SETTING

        self.core = FeatureFlagsCore()
        self.settings = carb.settings.get_settings()

        self.instance = get_instance()
        self.window_name = "Feature Flags"

        self._setup_flags_settings()
        await ui_test.human_delay()

        self.instance.show(True)

    # After running each test
    async def tearDown(self):
        self.instance.show(False)

        self.instance = None
        self.window_name = None

        # Cleanup the Feature Flag settings
        self.settings.destroy_item(self.settings_path)
        self.settings.destroy_item(self.persistent_path + self.settings_path)

        self.persistent_path = None
        self.settings_path = None

        self.core = None
        self.settings = None

    def _setup_flags_settings(self):
        # Transient Flag
        self.settings.set(f"{self.settings_path}/transient_test_flag/value", True)
        self.settings.set(f"{self.settings_path}/transient_test_flag/display_name", "Transient Flag Display Name")
        self.settings.set(f"{self.settings_path}/transient_test_flag/tooltip", "Transient Flag Tooltip")

        # Mixed Flag
        self.settings.set(f"{self.settings_path}/mixed_test_flag/value", False)
        self.settings.set(f"{self.settings_path}/mixed_test_flag/display_name", "Mixed Flag Display Name")
        self.settings.set(f"{self.settings_path}/mixed_test_flag/tooltip", "Mixed Flag Tooltip")

        self.settings.set(f"{self.persistent_path}{self.settings_path}/mixed_test_flag/value", True)

        # Persistent Flag
        self.settings.set(f"{self.persistent_path}{self.settings_path}/persistent_test_flag/value", True)
        self.settings.set(
            f"{self.persistent_path}{self.settings_path}/persistent_test_flag/display_name",
            "Persistent Flag Display Name",
        )
        self.settings.set(
            f"{self.persistent_path}{self.settings_path}/persistent_test_flag/tooltip", "Persistent Flag Tooltip"
        )

    async def test_enable_all_disable_all_update_settings_and_ui(self):
        # Setup a callback mock to make sure the events are triggered
        callback_mock = Mock()
        with self.core.feature_flags_changed(callback_mock):
            enable_button = ui_test.find(f"{self.window_name}//Frame/**/Button[*].identifier=='feature_flag_enable'")
            disable_button = ui_test.find(f"{self.window_name}//Frame/**/Button[*].identifier=='feature_flag_disable'")

            self.assertIsNotNone(enable_button)
            self.assertIsNotNone(disable_button)

            # Make sure all the features are enabled
            await enable_button.click()
            await ui_test.human_delay()

            checkboxes = ui_test.find_all(
                f"{self.window_name}//Frame/**/CheckBox[*].identifier=='feature_flag_checkbox'"
            )

            for checkbox in checkboxes:
                self.assertTrue(checkbox.widget.checked)

            self.assertTrue(self.core.is_enabled("transient_test_flag"))
            self.assertTrue(self.core.is_enabled("mixed_test_flag"))

            # Cleanup Persistent Flag + 2x Enable
            self.assertEqual(callback_mock.call_count, 3)

            # Disable all features
            await disable_button.click()
            await ui_test.human_delay()

            checkboxes = ui_test.find_all(
                f"{self.window_name}//Frame/**/CheckBox[*].identifier=='feature_flag_checkbox'"
            )

            for checkbox in checkboxes:
                self.assertFalse(checkbox.widget.checked)

            self.assertFalse(self.core.is_enabled("transient_test_flag"))
            self.assertFalse(self.core.is_enabled("mixed_test_flag"))

            # 2x Disable
            self.assertEqual(callback_mock.call_count, 5)

            # Enable all features by using the checkboxes
            checkboxes = ui_test.find_all(
                f"{self.window_name}//Frame/**/CheckBox[*].identifier=='feature_flag_checkbox'"
            )

            for checkbox in checkboxes:
                await checkbox.click()
                await ui_test.human_delay()

            checkboxes = ui_test.find_all(
                f"{self.window_name}//Frame/**/CheckBox[*].identifier=='feature_flag_checkbox'"
            )

            for checkbox in checkboxes:
                self.assertTrue(checkbox.widget.checked)

            self.assertTrue(self.core.is_enabled("transient_test_flag"))
            self.assertTrue(self.core.is_enabled("mixed_test_flag"))

            # 2x Enable
            self.assertEqual(callback_mock.call_count, 7)

            # Disable all features by using the checkboxes
            checkboxes = ui_test.find_all(
                f"{self.window_name}//Frame/**/CheckBox[*].identifier=='feature_flag_checkbox'"
            )

            for checkbox in checkboxes:
                await checkbox.click()
                await ui_test.human_delay()

            checkboxes = ui_test.find_all(
                f"{self.window_name}//Frame/**/CheckBox[*].identifier=='feature_flag_checkbox'"
            )

            for checkbox in checkboxes:
                self.assertFalse(checkbox.widget.checked)

            self.assertFalse(self.core.is_enabled("transient_test_flag"))
            self.assertFalse(self.core.is_enabled("mixed_test_flag"))

            # 2x Disable
            self.assertEqual(callback_mock.call_count, 9)
