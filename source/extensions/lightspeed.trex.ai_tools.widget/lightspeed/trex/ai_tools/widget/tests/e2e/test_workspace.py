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
from lightspeed.common.constants import WindowNames as _WindowNames
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


class TestAIToolsWorkspaceE2E(AsyncTestCase):
    async def test_show_window_after_hide_does_not_error(self):
        await arrange_windows()

        ui.Workspace.show_window(_WindowNames.AI_TOOLS, True)
        await ui_test.wait_n_updates(2)

        ui.Workspace.show_window(_WindowNames.AI_TOOLS, False)
        await ui_test.wait_n_updates(2)

        ui.Workspace.show_window(_WindowNames.AI_TOOLS, True)
        await ui_test.wait_n_updates(2)

        self.assertTrue(ui.Workspace.get_window(_WindowNames.AI_TOOLS).visible)

        ui.Workspace.show_window(_WindowNames.AI_TOOLS, False)
        await ui_test.wait_n_updates(2)
