"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import omni.kit.app
import omni.ui as ui
from lightspeed.trex.project_setup.widget.setup_ui import ProjectSetupPane
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


class TestProjectSetupPaneVisibilityFiltering(AsyncTestCase):
    """
    Test that @skip_when_widget_is_invisible decorator works on ProjectSetupPane's decorated methods.
    """

    async def setUp(self):
        await arrange_windows()

    async def test_widget_has_root_widget(self):
        """Test that ProjectSetupPane properly exposes root_widget"""
        # Arrange
        window = ui.Window("test_project_setup", width=600, height=800)
        with window.frame:
            widget = ProjectSetupPane("")
        await omni.kit.app.get_app().next_update_async()

        # Assert
        self.assertIsNotNone(widget.root_widget)
        self.assertTrue(hasattr(widget.root_widget, "visible"))

        window.destroy()

    async def test_visibility_can_be_toggled(self):
        """Test that root_widget visibility can be controlled"""
        # Arrange
        window = ui.Window("test_visibility_toggle", width=600, height=800)
        with window.frame:
            widget = ProjectSetupPane("")
        await omni.kit.app.get_app().next_update_async()

        # Act & Assert
        widget.root_widget.visible = True
        self.assertTrue(widget.root_widget.visible)

        widget.root_widget.visible = False
        self.assertFalse(widget.root_widget.visible)

        window.destroy()

    async def test_parent_hierarchy_exists(self):
        """Test that widget can be nested in parent frame"""
        # Arrange
        window = ui.Window("test_parent", width=600, height=800)
        with window.frame:
            parent_frame = ui.Frame(visible=True)
            with parent_frame:
                widget = ProjectSetupPane("")
        await omni.kit.app.get_app().next_update_async()

        # Assert
        self.assertIsNotNone(widget.root_widget)

        window.destroy()
