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

import omni.ui as ui
from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardInput
from omni.flux.validator.plugin.check.usd.texture.convert_to_dds import ConvertToDDS
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


class TestConvertToDDSUI(AsyncTestCase):
    """Exercise the regular ConvertToDDS plugin UI."""

    async def setUp(self):
        """Create the plugin's regular UI in a Kit window."""
        await arrange_windows()
        self._plugin = ConvertToDDS()
        self._data = ConvertToDDS.Data()
        self._window = ui.Window("TestConvertToDDSRegularUI", height=200, width=500)
        with self._window.frame:
            await self._plugin.build_ui(self._data)
        await ui_test.human_delay(human_delay_speed=1)

    async def tearDown(self):
        """Destroy the plugin UI after each workflow."""
        self._plugin.destroy()
        self._window.frame.clear()
        self._window.destroy()
        await ui_test.human_delay(human_delay_speed=1)

    async def test_edit_max_workers_in_regular_ui_updates_schema(self):
        """Editing the regular MaxWorkersField updates ConvertToDDS data."""
        fields = ui_test.find_all(f"{self._window.title}//Frame/**/IntField[*].identifier=='MaxWorkersField'")
        self.assertEqual(1, len(fields))

        await fields[0].click()
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.DEL)
        await ui_test.human_delay()
        await fields[0].input("3", end_key=KeyboardInput.ENTER)
        await ui_test.human_delay()

        self.assertEqual(3, fields[0].widget.model.get_value_as_int())
        self.assertEqual(3, self._data.max_workers)
