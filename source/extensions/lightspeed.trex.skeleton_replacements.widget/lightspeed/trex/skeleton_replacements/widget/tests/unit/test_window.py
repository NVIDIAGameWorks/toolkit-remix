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

from unittest.mock import MagicMock

import omni.kit.app
from omni.kit.test import AsyncTestCase

from lightspeed.trex.skeleton_replacements.widget.window import SkeletonRemappingWindow


class TestSkeletonRemappingWindow(AsyncTestCase):
    async def test_init_should_create_hidden_window_and_widget(self):
        # Arrange
        window = None

        # Act
        window = SkeletonRemappingWindow()
        await omni.kit.app.get_app().next_update_async()

        # Assert
        try:
            self.assertFalse(window.window.visible)
            self.assertIsNotNone(window._widget)
            self.assertIsNotNone(window._widget._tree)
        finally:
            window.destroy()

    async def test_show_window_with_replacement_should_refresh_widget_and_title(self):
        # Arrange
        window = SkeletonRemappingWindow.__new__(SkeletonRemappingWindow)
        window._widget = MagicMock()
        window.window = MagicMock()
        skel_replacement = MagicMock()
        skel_replacement.bound_prim.GetName.return_value = "replacement_mesh"
        skel_replacement.bound_prim.GetPath.return_value = "/RootNode/meshes/ref/replacement_mesh"

        # Act
        window.show_window(True, skel_replacement)

        # Assert
        self.assertTrue(window.window.visible)
        window._widget.refresh.assert_called_once_with(skel_replacement)
        self.assertEqual("Remap Skeleton Binding On: replacement_mesh", window.window.title)
        self.assertEqual(
            "Remap Skeleton Binding On: /RootNode/meshes/ref/replacement_mesh", window.window.tabBar_tooltip
        )

    async def test_show_window_with_hidden_value_should_not_refresh_widget(self):
        # Arrange
        window = SkeletonRemappingWindow.__new__(SkeletonRemappingWindow)
        window._widget = MagicMock()
        window.window = MagicMock()

        # Act
        window.show_window(False)

        # Assert
        self.assertFalse(window.window.visible)
        window._widget.refresh.assert_not_called()

    async def test_destroy_should_release_widget_and_destroy_window(self):
        # Arrange
        window = SkeletonRemappingWindow.__new__(SkeletonRemappingWindow)
        window._widget = MagicMock()
        window.window = MagicMock()
        widget = window._widget
        ui_window = window.window

        # Act
        window.destroy()

        # Assert
        widget.destroy.assert_not_called()
        ui_window.destroy.assert_called_once_with()
        self.assertIsNone(window._widget)
        self.assertIsNone(window.window)
