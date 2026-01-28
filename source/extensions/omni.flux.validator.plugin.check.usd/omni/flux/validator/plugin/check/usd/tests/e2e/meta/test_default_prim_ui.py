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

import omni.ui as ui
import omni.usd
from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
from omni.flux.validator.manager.widget import ValidatorManagerWidget as _ValidatorManagerWidget
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path, open_stage


class TestDefaultPrimUI(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()

    # After running each test
    async def tearDown(self):
        pass

    def _make_core(self):
        return _ManagerCore(
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "DefaultPrim",
                        "selector_plugins": [{"name": "Nothing", "data": {}}],
                        "data": {"manual_selection": True},
                        "context_plugin": {"name": "DependencyIterator", "data": {}},
                        "pause_if_fix_failed": False,
                        "stop_if_fix_failed": False,
                    }
                ],
            }
        )

    async def __make_ui(self, name, core):
        window = ui.Window(f"TestValidationUI{name}", height=800, width=400)
        with window.frame:
            wid = _ValidatorManagerWidget(core=core)

        await ui_test.human_delay(human_delay_speed=1)

        return window, wid

    async def __destroy_ui(self, window, wid):
        await ui_test.human_delay(human_delay_speed=1)
        wid.destroy()
        window.frame.clear()
        window.destroy()
        await ui_test.human_delay(human_delay_speed=1)

    async def test_run_manual_fix_1(self):
        # Arrange
        await open_stage(get_test_data_path(__name__, "usd/multiple_roots.usda"))
        core = self._make_core()
        window, wid = await self.__make_ui("test_run_manual_fix_1", core)

        # Act
        await core.deferred_run()

        expand_checks = ui_test.find_all(f"{window.title}//Frame/**/Image[*].identifier=='expand_plugin'")
        await expand_checks[0].click()
        prim_treeview = ui_test.find(f"{window.title}//Frame/**/TreeView[*].identifier=='default_prim_treeview'")
        prim_labels = prim_treeview.find_all("Label[*]")
        await prim_labels[1].click()

        # Assert
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        self.assertTrue(stage.HasDefaultPrim())
        self.assertEqual(stage.GetDefaultPrim().GetName(), "Cube2")

        await self.__destroy_ui(window, wid)

    async def test_run_manual_fix_2(self):
        # Test that the UI will update correctly
        # Arrange
        await open_stage(get_test_data_path(__name__, "usd/multiple_roots.usda"))
        core = self._make_core()
        window, wid = await self.__make_ui("test_run_manual_fix_2", core)

        # Act
        expand_checks = ui_test.find_all(f"{window.title}//Frame/**/Image[*].identifier=='expand_plugin'")
        await expand_checks[0].click()

        await core.deferred_run()

        prim_treeview = ui_test.find(f"{window.title}//Frame/**/TreeView[*].identifier=='default_prim_treeview'")
        prim_labels = prim_treeview.find_all("Label[*]")
        await prim_labels[1].click()

        # Assert
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        self.assertTrue(stage.HasDefaultPrim())
        self.assertEqual(stage.GetDefaultPrim().GetName(), "Cube2")

        await self.__destroy_ui(window, wid)
