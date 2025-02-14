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
from unittest.mock import Mock, call

import omni.kit.test
from lightspeed.trex.mod_packaging_layers.widget import ModPackagingLayersWidget
from omni import ui
from omni.kit import ui_test
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path, wait_stage_loading


class TestModPackagingLayersWidget(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.context = omni.usd.get_context()
        await self.context.open_stage_async(get_test_data_path(__name__, "usd/project.usda"))

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.context = None
        self.temp_dir.cleanup()
        self.temp_dir = None

    async def __setup_widget(self):
        await arrange_windows(topleft_window="Stage")

        window = ui.Window("TestModPackagingDetailsWindow", height=400, width=400)
        with window.frame:
            mod_layers = ModPackagingLayersWidget(context_name="")
        await ui_test.human_delay()
        mod_layers.show(True)

        return window, mod_layers

    async def __destroy_widget(self, window, widget):
        widget.destroy()
        window.destroy()

    async def test_toggling_layer_should_toggle_all_children(self):
        window, widget = await self.__setup_widget()

        await ui_test.human_delay(20)

        layers_validity_changed_mock = Mock()
        _ = widget.subscribe_layers_validity_changed(layers_validity_changed_mock)

        number_of_layers = 6

        await ui_test.human_delay(30)  # Give the widget time to expand
        select_layer_checkboxes = ui_test.find_all(f"{window.title}//Frame/**/CheckBox[*].identifier=='select_layer'")

        # Should have 1 checkbox per layer
        self.assertEqual(number_of_layers, len(select_layer_checkboxes))

        for i in range(number_of_layers):
            # The project & dependency should be disabled.
            # All other layers should be enabled because they're part of the main mod
            self.assertEqual(i not in (0, number_of_layers - 1), select_layer_checkboxes[i].widget.enabled)
            # All main mod layers should be selected by default
            self.assertEqual(i not in (0, number_of_layers - 1), select_layer_checkboxes[i].model.get_value_as_bool())

        # Deselect the root main mod
        await select_layer_checkboxes[1].click()
        await ui_test.human_delay()

        for i in range(number_of_layers):
            # All sublayers should be deselected too
            self.assertEqual(False, select_layer_checkboxes[i].model.get_value_as_bool())

        # Should be invalid since nothing is selected
        self.assertEqual(4, layers_validity_changed_mock.call_count)
        self.assertEqual(call(False), layers_validity_changed_mock.call_args)

        # Select the sublayer should select the sublayer child
        await select_layer_checkboxes[2].click()
        await ui_test.human_delay()

        for i in range(number_of_layers):
            # Only the sublayer & sublayer child should be selected
            self.assertEqual(i in [2, 3], select_layer_checkboxes[i].model.get_value_as_bool())

        # Should be invalid since nothing is selected
        self.assertEqual(6, layers_validity_changed_mock.call_count)
        self.assertEqual(call(True), layers_validity_changed_mock.call_args)

        await self.__destroy_widget(window, widget)

    async def test_packaged_layers_returns_layer_paths(self):
        window, widget = await self.__setup_widget()

        await ui_test.human_delay(20)  # Give the widget time to render

        packaged_layers = [
            get_test_data_path(__name__, "usd/mod.usda").lower(),
            get_test_data_path(__name__, "usd/sublayer.usda").lower(),
            get_test_data_path(__name__, "usd/sublayer_sibling.usda").lower(),
            get_test_data_path(__name__, "usd/sublayer_child.usda").lower(),
        ]

        self.assertListEqual(packaged_layers, [layer.lower() for layer in widget.packaged_layers])

        await self.__destroy_widget(window, widget)
