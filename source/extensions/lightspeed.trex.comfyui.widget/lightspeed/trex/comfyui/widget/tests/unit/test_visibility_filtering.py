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
from lightspeed.trex.comfyui.core import ComfyUIState
from lightspeed.trex.comfyui.widget.widget import ComfyUIWidget
from lightspeed.trex.utils.widget.decorators import SKIPPED
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


class TestComfyUIWidgetVisibilityFiltering(AsyncTestCase):
    """
    Test that @skip_when_widget_is_invisible decorator works on ComfyUIWidget's decorated methods.
    """

    async def setUp(self):
        await arrange_windows()

    async def test_decorated_methods_skip_when_invisible(self):
        """Test that decorated methods return _SKIPPED_ when widget is invisible"""
        # Arrange
        window = ui.Window("test_comfyui", width=600, height=800)
        with window.frame:
            widget = ComfyUIWidget("")
        await omni.kit.app.get_app().next_update_async()

        # Act & Assert: When visible
        widget.root_widget.visible = True
        await omni.kit.app.get_app().next_update_async()

        self.assertNotEqual(widget._on_state_changed(ComfyUIState.NOT_FOUND), SKIPPED)  # noqa: PLW0212
        self.assertNotEqual(widget._on_selection_changed([]), SKIPPED)  # noqa: PLW0212

        # Act & Assert: When invisible
        widget.root_widget.visible = False
        await omni.kit.app.get_app().next_update_async()

        self.assertEqual(widget._on_state_changed(ComfyUIState.FOUND), SKIPPED)  # noqa: PLW0212
        self.assertEqual(widget._on_selection_changed(["/test/path"]), SKIPPED)  # noqa: PLW0212

        window.destroy()

    async def test_skips_when_parent_frame_invisible(self):  # noqa: PLW0212
        """Test that callbacks skip when parent frame is invisible"""
        # Arrange
        window = ui.Window("test_parent_invisible", width=600, height=800)
        with window.frame:
            parent_frame = ui.Frame(visible=True)
            with parent_frame:
                widget = ComfyUIWidget("")
        await omni.kit.app.get_app().next_update_async()

        # Act & Assert: When both visible
        widget.root_widget.visible = True
        self.assertNotEqual(widget._on_state_changed(ComfyUIState.NOT_FOUND), SKIPPED)  # noqa: PLW0212

        # Act & Assert: When parent invisible
        parent_frame.visible = False
        await omni.kit.app.get_app().next_update_async()
        self.assertEqual(widget._on_state_changed(ComfyUIState.FOUND), SKIPPED)  # noqa: PLW0212

        window.destroy()

    async def test_skips_when_window_invisible(self):
        """Test that callbacks skip when window is invisible"""
        # Arrange
        window = ui.Window("test_window_invisible", width=600, height=800, visible=True)
        with window.frame:
            widget = ComfyUIWidget("")
        await omni.kit.app.get_app().next_update_async()

        # Act & Assert: When window visible
        widget.root_widget.visible = True
        self.assertNotEqual(widget._on_state_changed(ComfyUIState.NOT_FOUND), SKIPPED)  # noqa: PLW0212

        # Act & Assert: When window invisible
        window.visible = False
        await omni.kit.app.get_app().next_update_async()
        self.assertEqual(widget._on_state_changed(ComfyUIState.FOUND), SKIPPED)  # noqa: PLW0212

        window.destroy()
