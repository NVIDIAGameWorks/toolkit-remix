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
from omni.flux.stage_manager.factory.plugins.tree_plugin import (
    StageManagerTreeItem,
    StageManagerTreeItemProxy,
    StageManagerTreeModel,
    TreeRefreshResult,
)
from omni.flux.stage_manager.plugin.widget.usd.action_is_visible import IsVisibleActionWidgetPlugin
from pxr import Usd, UsdGeom

__all__ = ["TestIsVisibleActionWidgetPlugin"]

_MODULE = "omni.flux.stage_manager.plugin.widget.usd.action_is_visible"


class _TreeItem(StageManagerTreeItem):
    """Provide canonical action rows without constructing UI."""

    @property
    def default_attr(self):
        """Return inherited cleanup attributes."""
        return super().default_attr


class _TreeModel(StageManagerTreeModel):
    """Publish action rows through the real model."""

    @property
    def default_attr(self):
        """Return inherited cleanup attributes."""
        return super().default_attr


class TestIsVisibleActionWidgetPlugin(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        """Keep fixture prims alive for each action test."""
        self._stage = Usd.Stage.CreateInMemory()

    def _make_plugin(self):
        return IsVisibleActionWidgetPlugin()

    def _make_item(self, prim_path="/World/Prim"):
        """Create a canonical row with valid prim data."""
        data = UsdGeom.Xform.Define(self._stage, prim_path).GetPrim()
        return _TreeItem(prim_path, data, path=prim_path)

    def _make_model(self, item, selected_paths: list[str] | None = None):
        """Publish canonical rows before assigning the selected proxies."""
        selected_items = [item if path == item.path else self._make_item(path) for path in selected_paths or []]
        items = selected_items if any(selected is item for selected in selected_items) else [*selected_items, item]
        proxies = [StageManagerTreeItemProxy(row) for row in items]
        model = _TreeModel()
        model.publish_refresh_result(
            TreeRefreshResult(
                canonical_root_items=items,
                root_items=proxies,
                items_by_path={},
                item_by_hash={hash(proxy): proxy for proxy in proxies},
                path_by_hash={},
                visible_items_count=len(items),
                visible_non_virtual_items_count=len(items),
                input_items_count=len(items),
                output_items_count=len(items),
            )
        )
        model.selection = [selected.proxy for selected in selected_items]
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
        model = self._make_model(item, selected_paths=[])

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
    # Group 3 — path resolution via _get_action_items
    # ------------------------------------------------------------------

    async def test_on_icon_clicked_unselected_item_should_use_only_clicked_item(self):
        # Arrange: item D is NOT in the current selection [A, B, C].
        # The action should act on D alone — not on the full selection.
        plugin = self._make_plugin()
        item = self._make_item("/World/D")
        model = self._make_model(item, selected_paths=["/World/A", "/World/B", "/World/C"])

        with (
            patch(f"{_MODULE}.UsdGeom") as mock_usdgeom,
            patch("omni.kit.commands.execute") as mock_execute,
        ):
            mock_usdgeom.Imageable.return_value.ComputeVisibility.return_value = Mock()
            plugin._on_icon_clicked(0, True, model, item)

        # Assert: only the clicked item, not the union
        called_paths = set(mock_execute.call_args.kwargs["selected_paths"])
        self.assertEqual(called_paths, {"/World/D"})

    async def test_on_icon_clicked_selected_item_should_filter_invalid_and_non_imageable_selection(self):
        # Arrange
        plugin = self._make_plugin()
        item = self._make_item("/World/A")
        model = self._make_model(item, selected_paths=["/World/A", "/World/B", "/World/C"])
        self._stage.RemovePrim("/World/B")
        self._stage.GetPrimAtPath("/World/C").ClearTypeName()

        with (
            patch(f"{_MODULE}.UsdGeom") as mock_usdgeom,
            patch("omni.kit.commands.execute") as mock_execute,
        ):
            mock_usdgeom.Imageable.return_value.ComputeVisibility.return_value = Mock()
            plugin._on_icon_clicked(0, True, model, item)

        # Assert: invalid and non-Imageable rows cannot receive visibility commands.
        called_paths = set(mock_execute.call_args.kwargs["selected_paths"])
        self.assertEqual(called_paths, {"/World/A"})

    async def test_on_icon_clicked_empty_selection_should_use_only_clicked_item(self):
        # Arrange
        plugin = self._make_plugin()
        item = self._make_item("/World/D")
        model = self._make_model(item, selected_paths=[])

        with (
            patch(f"{_MODULE}.UsdGeom") as mock_usdgeom,
            patch("omni.kit.commands.execute") as mock_execute,
        ):
            mock_usdgeom.Imageable.return_value.ComputeVisibility.return_value = Mock()
            plugin._on_icon_clicked(0, True, model, item)

        # Assert
        called_paths = set(mock_execute.call_args.kwargs["selected_paths"])
        self.assertEqual(called_paths, {"/World/D"})

    async def test_on_icon_clicked_item_without_data_should_not_execute_command(self):
        # Arrange
        plugin = self._make_plugin()
        item = _TreeItem("Group", None)
        model = self._make_model(item, selected_paths=["/World/A"])

        with (
            patch(f"{_MODULE}.UsdGeom") as mock_usdgeom,
            patch("omni.kit.commands.execute") as mock_execute,
        ):
            mock_usdgeom.Imageable.return_value.ComputeVisibility.return_value = Mock()
            plugin._on_icon_clicked(0, True, model, item)

        # Assert
        mock_execute.assert_not_called()

    # ------------------------------------------------------------------
    # Group 4 — model selection must NOT be modified
    # ------------------------------------------------------------------

    async def test_on_icon_clicked_should_not_modify_model_selection(self):
        # The action widget must read selection without mutating it.
        plugin = self._make_plugin()
        item = self._make_item("/World/D")
        model = self._make_model(item, selected_paths=["/World/A"])
        original_selection = list(model.selection)

        with (
            patch(f"{_MODULE}.UsdGeom") as mock_usdgeom,
            patch("omni.kit.commands.execute"),
        ):
            mock_usdgeom.Imageable.return_value.ComputeVisibility.return_value = Mock()
            plugin._on_icon_clicked(0, True, model, item)

        # Assert: model.selection was not mutated
        self.assertEqual(model.selection, original_selection)
