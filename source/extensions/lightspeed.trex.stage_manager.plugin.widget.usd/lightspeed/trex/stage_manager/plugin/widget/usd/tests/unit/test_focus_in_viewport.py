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
from lightspeed.common.constants import GlobalEventNames
from lightspeed.trex.stage_manager.plugin.widget.usd.focus_in_viewport import (
    FocusInViewportActionWidgetPlugin,
    _frame_paths_in_viewport,
)
from omni.flux.stage_manager.factory import StageManagerTreeItemProxy

__all__ = ["TestFocusInViewportActionWidgetPlugin"]

_MODULE = "lightspeed.trex.stage_manager.plugin.widget.usd.focus_in_viewport"


class TestFocusInViewportActionWidgetPlugin(omni.kit.test.AsyncTestCase):
    def _make_plugin(self, context_name: str = "") -> FocusInViewportActionWidgetPlugin:
        """Create a plugin bound to the requested USD context."""
        plugin = FocusInViewportActionWidgetPlugin()
        plugin.set_context_name(context_name)
        return plugin

    def _make_item(self, prim_path: str = "/World/Prim") -> Mock:
        """Create an imageable tree item with the requested prim path."""
        item = Mock()
        item.data = Mock()
        item.data.GetPath.return_value = prim_path
        return item

    def _make_model(self, selected_paths: list[str] | None = None) -> Mock:
        """Create a model whose selection reflects the requested prim paths."""
        model = Mock()
        if selected_paths is not None:
            model.selection = [StageManagerTreeItemProxy(self._make_item(path)) for path in selected_paths]
        else:
            model.selection = []
        return model

    async def test_on_icon_clicked_non_left_button_does_not_frame_paths(self):
        # Arrange
        plugin = self._make_plugin()
        item = self._make_item()
        model = Mock()

        # Act
        with patch(f"{_MODULE}._frame_paths_in_viewport") as mock_frame_paths_in_viewport:
            plugin._on_icon_clicked(1, True, model, item)  # button=1

        # Assert
        mock_frame_paths_in_viewport.assert_not_called()

    async def test_on_icon_clicked_disabled_does_not_frame_paths(self):
        # Arrange
        plugin = self._make_plugin()
        item = self._make_item()
        model = Mock()

        # Act
        with patch(f"{_MODULE}._frame_paths_in_viewport") as mock_frame_paths_in_viewport:
            plugin._on_icon_clicked(0, False, model, item)  # enabled=False

        # Assert
        mock_frame_paths_in_viewport.assert_not_called()

    async def test_on_icon_clicked_does_not_select_item(self):
        # Arrange
        plugin = self._make_plugin()
        item = self._make_item("/World/D")
        model = self._make_model(selected_paths=[])

        with (
            patch(f"{_MODULE}._frame_paths_in_viewport"),
            patch.object(plugin, "_item_clicked") as mock_item_clicked,
        ):
            # Act
            plugin._on_icon_clicked(0, True, model, item)

        # Assert
        mock_item_clicked.assert_not_called()

    async def test_on_icon_clicked_selected_item_frames_selection_in_plugin_context(self):
        # Arrange
        plugin = self._make_plugin("texturecraft")
        item = self._make_item("/World/A")
        model = self._make_model(selected_paths=["/World/A", "/World/B", "/World/C"])

        with patch(f"{_MODULE}._frame_paths_in_viewport") as mock_frame_paths_in_viewport:
            # Act
            plugin._on_icon_clicked(0, True, model, item)

        # Assert
        mock_frame_paths_in_viewport.assert_called_once_with(["/World/A", "/World/B", "/World/C"], "texturecraft")

    async def test_on_icon_clicked_unselected_item_frames_only_clicked_path(self):
        # Arrange
        plugin = self._make_plugin("texturecraft")
        item = self._make_item("/World/D")
        model = self._make_model(selected_paths=["/World/A", "/World/B", "/World/C"])

        with patch(f"{_MODULE}._frame_paths_in_viewport") as mock_frame_paths_in_viewport:
            # Act
            plugin._on_icon_clicked(0, True, model, item)

        # Assert
        mock_frame_paths_in_viewport.assert_called_once_with(["/World/D"], "texturecraft")

    async def test_frame_paths_in_viewport_emits_context_bound_request(self):
        # Arrange
        event_manager = Mock()
        paths = ["/World/A", "/World/B"]

        with patch(f"{_MODULE}._get_event_manager_instance", return_value=event_manager):
            # Act
            _frame_paths_in_viewport(paths, "texturecraft")

        # Assert
        event_manager.call_global_custom_event.assert_called_once_with(
            GlobalEventNames.VIEWPORT_FRAME_PRIMS_REQUEST.value,
            paths,
            "texturecraft",
        )

    async def test_on_frame_on_the_viewport_frames_usd_selection_in_payload_context(self):
        # Arrange
        usd_selection = ["/World/A", "/World/B"]
        payload = {"context_name": "ingestcraft", "paths": ["/World/D"]}
        with (
            patch(f"{_MODULE}.usd") as mock_usd,
            patch(f"{_MODULE}._frame_paths_in_viewport") as mock_frame_paths_in_viewport,
        ):
            mock_usd.get_context.return_value.get_selection.return_value.get_selected_prim_paths.return_value = (
                usd_selection
            )

            # Act
            FocusInViewportActionWidgetPlugin._on_frame_on_the_viewport(payload)

        # Assert
        mock_usd.get_context.assert_called_once_with("ingestcraft")
        mock_frame_paths_in_viewport.assert_called_once_with(usd_selection, "ingestcraft")

    async def test_on_frame_on_the_viewport_missing_context_logs_error_without_framing(self):
        # Arrange
        payload = {"context_name": "missing_ctx"}

        with (
            patch(f"{_MODULE}.usd") as mock_usd,
            patch(f"{_MODULE}.carb") as mock_carb,
            patch(f"{_MODULE}._frame_paths_in_viewport") as mock_frame_paths_in_viewport,
        ):
            mock_usd.get_context.return_value = None  # no context found

            # Act
            FocusInViewportActionWidgetPlugin._on_frame_on_the_viewport(payload)

        # Assert
        mock_carb.log_error.assert_called_once()
        mock_frame_paths_in_viewport.assert_not_called()
