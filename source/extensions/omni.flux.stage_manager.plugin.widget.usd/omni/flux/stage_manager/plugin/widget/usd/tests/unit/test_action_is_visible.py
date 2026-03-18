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

from unittest.mock import Mock, patch

import omni.kit.test
from omni.flux.stage_manager.plugin.widget.usd.action_is_visible import IsVisibleActionWidgetPlugin

__all__ = ["TestIsVisibleActionWidgetPlugin"]

_MODULE = "omni.flux.stage_manager.plugin.widget.usd.action_is_visible"


class TestIsVisibleActionWidgetPlugin(omni.kit.test.AsyncTestCase):
    def _make_plugin(self):
        return IsVisibleActionWidgetPlugin()

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
    # Group 1 — early-exit guards
    # ------------------------------------------------------------------

    async def test_on_icon_clicked_non_left_button_should_not_execute_command(self):
        # Arrange
        plugin = self._make_plugin()
        item = self._make_item()
        model = Mock()

        # Act
        with patch("omni.kit.commands.execute") as mock_execute:
            plugin._on_icon_clicked(1, True, model, item)  # button=1

        # Assert
        mock_execute.assert_not_called()

    async def test_on_icon_clicked_disabled_should_not_execute_command(self):
        # Arrange
        plugin = self._make_plugin()
        item = self._make_item()
        model = Mock()

        # Act
        with patch("omni.kit.commands.execute") as mock_execute:
            plugin._on_icon_clicked(0, False, model, item)  # enabled=False

        # Assert
        mock_execute.assert_not_called()

    # ------------------------------------------------------------------
    # Group 2 — _item_clicked must NOT be called
    # ------------------------------------------------------------------

    async def test_on_icon_clicked_should_not_call_item_clicked(self):
        # Arrange
        plugin = self._make_plugin()
        item = self._make_item("/World/D")
        model = self._make_model(selected_paths=[])

        with (
            patch(f"{_MODULE}.UsdGeom") as mock_usdgeom,
            patch("omni.kit.commands.execute"),
            patch.object(plugin, "_item_clicked") as mock_item_clicked,
        ):
            mock_usdgeom.Imageable.return_value.ComputeVisibility.return_value = Mock()
            plugin._on_icon_clicked(0, True, model, item)

        # Assert
        mock_item_clicked.assert_not_called()

    # ------------------------------------------------------------------
    # Group 3 — path resolution via _get_action_paths
    # ------------------------------------------------------------------

    async def test_on_icon_clicked_unselected_item_should_use_only_clicked_item(self):
        # Arrange: item D is NOT in the current selection [A, B, C].
        # The action should act on D alone — not on the full selection.
        plugin = self._make_plugin()
        item = self._make_item("/World/D")
        model = self._make_model(selected_paths=["/World/A", "/World/B", "/World/C"])

        with (
            patch(f"{_MODULE}.UsdGeom") as mock_usdgeom,
            patch("omni.kit.commands.execute") as mock_execute,
        ):
            mock_usdgeom.Imageable.return_value.ComputeVisibility.return_value = Mock()
            plugin._on_icon_clicked(0, True, model, item)

        # Assert: only the clicked item, not the union
        called_paths = set(mock_execute.call_args.kwargs["selected_paths"])
        self.assertEqual(called_paths, {"/World/D"})

    async def test_on_icon_clicked_selected_item_should_use_full_selection(self):
        # Arrange: item A IS in the current selection [A, B, C].
        # The action should act on all selected items.
        plugin = self._make_plugin()
        item = self._make_item("/World/A")
        model = self._make_model(selected_paths=["/World/A", "/World/B", "/World/C"])

        with (
            patch(f"{_MODULE}.UsdGeom") as mock_usdgeom,
            patch("omni.kit.commands.execute") as mock_execute,
        ):
            mock_usdgeom.Imageable.return_value.ComputeVisibility.return_value = Mock()
            plugin._on_icon_clicked(0, True, model, item)

        # Assert: full selection used
        called_paths = set(mock_execute.call_args.kwargs["selected_paths"])
        self.assertEqual(called_paths, {"/World/A", "/World/B", "/World/C"})

    async def test_on_icon_clicked_empty_selection_should_use_only_clicked_item(self):
        # Arrange
        plugin = self._make_plugin()
        item = self._make_item("/World/D")
        model = self._make_model(selected_paths=[])

        with (
            patch(f"{_MODULE}.UsdGeom") as mock_usdgeom,
            patch("omni.kit.commands.execute") as mock_execute,
        ):
            mock_usdgeom.Imageable.return_value.ComputeVisibility.return_value = Mock()
            plugin._on_icon_clicked(0, True, model, item)

        # Assert
        called_paths = set(mock_execute.call_args.kwargs["selected_paths"])
        self.assertEqual(called_paths, {"/World/D"})

    async def test_on_icon_clicked_item_without_data_should_use_current_selection(self):
        # Arrange: item.data=None — hypothetical defensive case. Falls back to selection.
        plugin = self._make_plugin()
        item = Mock()
        item.data = None
        model = self._make_model(selected_paths=["/World/A"])

        with (
            patch(f"{_MODULE}.UsdGeom") as mock_usdgeom,
            patch("omni.kit.commands.execute") as mock_execute,
        ):
            mock_usdgeom.Imageable.return_value.ComputeVisibility.return_value = Mock()
            plugin._on_icon_clicked(0, True, model, item)

        # Assert: falls back to current selection
        called_paths = set(mock_execute.call_args.kwargs["selected_paths"])
        self.assertEqual(called_paths, {"/World/A"})

    # ------------------------------------------------------------------
    # Group 4 — model selection must NOT be modified
    # ------------------------------------------------------------------

    async def test_on_icon_clicked_should_not_modify_model_selection(self):
        # The action widget must read selection without mutating it.
        plugin = self._make_plugin()
        item = self._make_item("/World/D")
        model = self._make_model(selected_paths=["/World/A"])
        original_selection = list(model.selection)

        with (
            patch(f"{_MODULE}.UsdGeom") as mock_usdgeom,
            patch("omni.kit.commands.execute"),
        ):
            mock_usdgeom.Imageable.return_value.ComputeVisibility.return_value = Mock()
            plugin._on_icon_clicked(0, True, model, item)

        # Assert: model.selection was not mutated
        self.assertEqual(model.selection, original_selection)
