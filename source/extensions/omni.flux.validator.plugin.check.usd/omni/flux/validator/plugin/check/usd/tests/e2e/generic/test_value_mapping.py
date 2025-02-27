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


class TestValueMappingE2E(AsyncTestCase):
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
                        "name": "ValueMapping",
                        "context_plugin": {"name": "DependencyIterator", "data": {}},
                        "selector_plugins": [{"name": "AllShaders", "data": {}}],
                        "data": {
                            "attributes": {
                                "inputs:emissive_intensity": [
                                    {"operator": "=", "input_value": 5.0, "output_value": 1.0},
                                    {"operator": "=", "input_value": 10.0, "output_value": 2.0},
                                ],
                                "info:mdl:sourceAsset:subIdentifier": [
                                    {"operator": "=", "input_value": "OmniPBRTest", "output_value": "OmniPBROutput"},
                                ],
                                "inputs:diffuse_color_constant": [
                                    {"operator": "=", "input_value": [0.1, 0.1, 0.1], "output_value": [1.0, 1.0, 1.0]},
                                ],
                            }
                        },
                        "pause_if_fix_failed": False,
                        "stop_if_fix_failed": False,
                    }
                ],
            }
        )

    async def __make_ui(self, name, core):
        window = ui.Window(f"TestValidationUI{name}", height=800, width=800)
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

    async def test_run_modify_mapping_parameters(self):
        # Arrange
        await open_stage(get_test_data_path(__name__, "usd/value_remap.usda"))
        core = self._make_core()
        window, wid = await self.__make_ui("modify_mapping_parameters", core)

        output_identifier = "TestIdentifier"
        input_value = "0.5"

        # Act
        # Show the plugin UI
        expand_checks = ui_test.find_all(f"{window.title}//Frame/**/Image[*].identifier=='expand_plugin'")
        self.assertGreater(len(expand_checks), 0)

        await expand_checks[0].click()
        await ui_test.human_delay()

        # Modify the query operator
        operator_fields = ui_test.find_all(f"{window.title}//Frame/**/ComboBox[*].identifier=='OperatorField'")
        self.assertEqual(len(operator_fields), 4)
        combobox = operator_fields[1]
        self.assertEqual(2, combobox.widget.model.get_item_value_model().get_value_as_int())
        combobox.widget.model.get_item_value_model().set_value(5)
        await ui_test.human_delay()

        # Modify the output value
        output_fields = ui_test.find_all(f"{window.title}//Frame/**/StringField[*].identifier=='OutputField'")
        self.assertEqual(len(output_fields), 6)
        await ui_test.human_delay(75)
        await output_fields[2].input(output_identifier)
        await ui_test.human_delay()

        # Modify the input values
        input_fields = ui_test.find_all(f"{window.title}//Frame/**/StringField[*].identifier=='InputField'")
        self.assertEqual(len(input_fields), 6)
        await input_fields[3].input(input_value)
        await input_fields[4].input(input_value)
        await input_fields[5].input(input_value)
        await ui_test.human_delay()

        # Run the Validation
        await core.deferred_run()

        # Assert
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()

        attr_0 = stage.GetPrimAtPath("/Looks/EqualRemap/Shader").GetAttribute("inputs:emissive_intensity")
        self.assertEqual(attr_0.Get(), 1.0)

        attr_1 = stage.GetPrimAtPath("/Looks/LargerRemap/Shader").GetAttribute("inputs:emissive_intensity")
        self.assertEqual(attr_1.Get(), 2.0)

        attr_2 = stage.GetPrimAtPath("/Looks/StringRemap/Shader").GetAttribute("info:mdl:sourceAsset:subIdentifier")
        self.assertEqual(attr_2.Get(), output_identifier)

        attr_3 = stage.GetPrimAtPath("/Looks/ColorRemap/Shader").GetAttribute("inputs:diffuse_color_constant")
        self.assertEqual(attr_3.Get(), (1.0, 1.0, 1.0))

        await self.__destroy_ui(window, wid)
