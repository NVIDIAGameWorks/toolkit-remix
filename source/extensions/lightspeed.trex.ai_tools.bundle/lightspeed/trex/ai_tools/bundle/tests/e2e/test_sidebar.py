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

from pathlib import Path

from lightspeed.common.constants import LayoutFiles, WindowNames
from lightspeed.trex.sidebar.setup_ui import SetupUI
from lightspeed.trex.sidebar import Groups, get_items
from omni import ui, usd
from omni.flux.utils.widget.resources import get_quicklayout_config
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase


class TestAIToolsSidebarE2E(AsyncTestCase):
    """Tests the live extension registration and packaged AI Tools layout."""

    async def test_extension_registers_sidebar_item_with_real_layout(self):
        """The loaded extension contributes one actionable AI Tools layout entry."""
        # Read the live sidebar registry and resolve the layout packaged by the loaded extension.
        layouts = get_items(Groups.LAYOUTS).get(Groups.LAYOUTS, [])

        ai_tools_items = [item for item in layouts if item.name == "AITools"]
        layout_path = get_quicklayout_config(LayoutFiles.TEXTURECRAFT)

        # One actionable entry points at a real layout file instead of an in-test substitute.
        self.assertEqual(len(ai_tools_items), 1)
        self.assertEqual(ai_tools_items[0].tooltip, "AI Tools")
        self.assertTrue(ai_tools_items[0].enabled)
        self.assertTrue(callable(ai_tools_items[0].mouse_released_fn))
        self.assertIsNotNone(layout_path)
        self.assertTrue(Path(layout_path).is_file())

    async def test_real_sidebar_opens_texturecraft_layout_without_project(self):
        """The rendered AI Tools action remains available without an open project."""
        context = usd.get_context("")
        if context.get_stage() is not None:
            await context.close_stage_async()
        window = ui.Window("ai_tools_sidebar_e2e", width=100, height=400)
        sidebar = SetupUI(window.frame)
        await ui_test.human_delay()

        try:
            # With no stage or project, the live action remains available for setup and queue management.
            button = ui_test.find("ai_tools_sidebar_e2e//Frame/**/Image[*].name=='AITools'")
            self.assertIsNotNone(button)
            self.assertEqual(button.widget.tooltip, "AI Tools")

            # Click the live sidebar entry and let QuickLayout create the packaged workspace.
            await button.click()
            await ui_test.human_delay(10)

            # Every product window declared by the layout is now present and visible.
            for title in (
                WindowNames.COMFYUI_SETUP,
                WindowNames.COMFYUI_WORKFLOW,
                WindowNames.JOB_QUEUE,
                WindowNames.JOB_DETAILS,
            ):
                layout_window = ui.Workspace.get_window(title)
                self.assertIsNotNone(layout_window, f"The packaged layout did not create '{title}'")
                self.assertTrue(layout_window.visible, f"The packaged layout did not show '{title}'")

            # Job Details occupies the full right column while the other tools remain entirely to its left.
            setup_window = ui.Workspace.get_window(WindowNames.COMFYUI_SETUP)
            workflow_window = ui.Workspace.get_window(WindowNames.COMFYUI_WORKFLOW)
            queue_window = ui.Workspace.get_window(WindowNames.JOB_QUEUE)
            details_window = ui.Workspace.get_window(WindowNames.JOB_DETAILS)
            self.assertAlmostEqual(details_window.position_y, setup_window.position_y, delta=1)
            self.assertAlmostEqual(
                details_window.position_y + details_window.height,
                workflow_window.position_y + workflow_window.height,
                delta=1,
            )
            self.assertLessEqual(queue_window.position_x + queue_window.width, details_window.position_x)
        finally:
            sidebar.destroy()
            window.destroy()
            if context.get_stage() is not None:
                await context.close_stage_async()
            await ui_test.human_delay()
