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

import omni.usd
from carb.input import KeyboardInput
from lightspeed.trex.contexts.extension import get_instance as get_context_manager
from lightspeed.trex.contexts.setup import Contexts
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage


class TestHotkeys(AsyncTestCase):

    async def setUp(self):
        trex_context_manager = get_context_manager()
        trex_context_manager.set_current_context(Contexts.TEXTURE_CRAFT)
        await open_stage(_get_test_data("usd/project_example/combined.usda"))

    async def test_unselect_all_with_esc(self):
        # Setup
        usd_context = omni.usd.get_context()

        # Select an object and ensure it is selected
        expected_value = ["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"]
        usd_context.get_selection().set_selected_prim_paths(expected_value, False)
        self.assertListEqual(usd_context.get_selection().get_selected_prim_paths(), expected_value)

        # Use the ESC hotkey to unselect everything
        await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
        await ui_test.human_delay(human_delay_speed=10)

        # Ensure that nothing is selected
        self.assertListEqual(usd_context.get_selection().get_selected_prim_paths(), [])
