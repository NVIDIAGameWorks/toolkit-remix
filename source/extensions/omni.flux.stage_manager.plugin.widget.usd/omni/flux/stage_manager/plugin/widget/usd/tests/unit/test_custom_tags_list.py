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

from unittest.mock import MagicMock, Mock, patch

import omni.kit.test
from omni.flux.stage_manager.plugin.widget.usd.custom_tags_list import CustomTagsWidgetPlugin

__all__ = ["TestCustomTagsWidgetPlugin"]

_MODULE = "omni.flux.stage_manager.plugin.widget.usd.custom_tags_list"


class TestCustomTagsWidgetPlugin(omni.kit.test.AsyncTestCase):
    def _make_plugin(self):
        return CustomTagsWidgetPlugin()

    def _make_item(self, prim_path="/World/Prim"):
        item = Mock()
        item.data = Mock()
        item.data.GetPath.return_value = prim_path
        return item

    def _make_model(self, selected_paths: list[str] | None = None):
        """Return a mock model whose .selection reflects the given prim paths."""
        model = Mock()
        if selected_paths is not None:
            model.selection = [self._make_item(p) for p in selected_paths]
        else:
            model.selection = []
        return model

    # ------------------------------------------------------------------
    # Group 1 — ScrollingFrame must have no mouse_pressed_fn
    # ------------------------------------------------------------------

    async def test_build_frame_scrolling_frame_has_no_mouse_pressed_fn(self):
        # Arrange
        plugin = self._make_plugin()
        model = Mock()
        item = self._make_item()

        with patch(f"{_MODULE}.ui") as mock_ui, patch(f"{_MODULE}.CustomTagsCore") as mock_core:
            mock_core.return_value.get_prim_tags.return_value = []
            # All ui.X(...) calls return MagicMock which supports context manager protocol
            mock_ui.HStack.return_value = MagicMock()
            mock_ui.VStack.return_value = MagicMock()
            mock_ui.ZStack.return_value = MagicMock()
            mock_ui.ScrollingFrame.return_value = MagicMock()

            # Act
            plugin._build_frame(model, item)

        # Assert: ScrollingFrame constructor was called without mouse_pressed_fn
        self.assertTrue(mock_ui.ScrollingFrame.called)
        for call in mock_ui.ScrollingFrame.call_args_list:
            self.assertNotIn("mouse_pressed_fn", call.kwargs)

    # ------------------------------------------------------------------
    # Group 2 — _open_edit_window: _item_clicked must NOT be called
    # ------------------------------------------------------------------

    async def test_open_edit_window_non_left_button_should_do_nothing(self):
        # Arrange
        plugin = self._make_plugin()
        model = Mock()
        item = self._make_item()

        with patch(f"{_MODULE}.EditCustomTagsWindow") as mock_window:
            # Act
            plugin._open_edit_window(model, item, 0, 0, 1, 0)  # b=1

        # Assert
        mock_window.assert_not_called()

    async def test_open_edit_window_should_not_call_item_clicked(self):
        # Arrange
        plugin = self._make_plugin()
        model = self._make_model(selected_paths=[])
        item = self._make_item("/World/D")

        with (
            patch(f"{_MODULE}.EditCustomTagsWindow"),
            patch.object(plugin, "_item_clicked") as mock_item_clicked,
        ):
            plugin._open_edit_window(model, item, 0, 0, 0, 0)

        # Assert
        mock_item_clicked.assert_not_called()

    # ------------------------------------------------------------------
    # Group 3 — _open_edit_window: path resolution via _get_action_paths
    # ------------------------------------------------------------------

    async def test_open_edit_window_unselected_item_should_use_only_clicked_item(self):
        # Arrange: item D is NOT in the current selection [A, B, C].
        plugin = self._make_plugin()
        model = self._make_model(selected_paths=["/World/A", "/World/B", "/World/C"])
        item = self._make_item("/World/D")

        with patch(f"{_MODULE}.EditCustomTagsWindow") as mock_window:
            plugin._open_edit_window(model, item, 0, 0, 0, 0)

        # Assert: only the clicked item, not the union
        passed_paths = set(mock_window.call_args.args[0])
        self.assertEqual(passed_paths, {"/World/D"})

    async def test_open_edit_window_selected_item_should_use_full_selection(self):
        # Arrange: item A IS in the current selection [A, B, C].
        plugin = self._make_plugin()
        model = self._make_model(selected_paths=["/World/A", "/World/B", "/World/C"])
        item = self._make_item("/World/A")

        with patch(f"{_MODULE}.EditCustomTagsWindow") as mock_window:
            plugin._open_edit_window(model, item, 0, 0, 0, 0)

        # Assert: full selection used
        passed_paths = set(mock_window.call_args.args[0])
        self.assertEqual(passed_paths, {"/World/A", "/World/B", "/World/C"})

    async def test_open_edit_window_empty_selection_should_use_only_clicked_item(self):
        # Arrange
        plugin = self._make_plugin()
        model = self._make_model(selected_paths=[])
        item = self._make_item("/World/D")

        with patch(f"{_MODULE}.EditCustomTagsWindow") as mock_window:
            plugin._open_edit_window(model, item, 0, 0, 0, 0)

        # Assert
        passed_paths = set(mock_window.call_args.args[0])
        self.assertEqual(passed_paths, {"/World/D"})

    async def test_open_edit_window_item_without_data_should_use_current_selection(self):
        # Arrange
        plugin = self._make_plugin()
        model = self._make_model(selected_paths=["/World/A"])
        item = Mock()
        item.data = None

        with patch(f"{_MODULE}.EditCustomTagsWindow") as mock_window:
            plugin._open_edit_window(model, item, 0, 0, 0, 0)

        # Assert
        passed_paths = set(mock_window.call_args.args[0])
        self.assertEqual(passed_paths, {"/World/A"})
