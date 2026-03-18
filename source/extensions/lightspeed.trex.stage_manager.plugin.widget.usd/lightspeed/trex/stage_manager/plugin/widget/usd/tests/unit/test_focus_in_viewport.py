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
from lightspeed.trex.stage_manager.plugin.widget.usd.focus_in_viewport import FocusInViewportActionWidgetPlugin

__all__ = ["TestFocusInViewportActionWidgetPlugin"]

_MODULE = "lightspeed.trex.stage_manager.plugin.widget.usd.focus_in_viewport"


class TestFocusInViewportActionWidgetPlugin(omni.kit.test.AsyncTestCase):
    def _make_plugin(self):
        return FocusInViewportActionWidgetPlugin()

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

    async def test_on_icon_clicked_non_left_button_should_not_call_frame_method(self):
        # Arrange
        plugin = self._make_plugin()
        item = self._make_item()
        model = Mock()

        # Act
        with patch(f"{_MODULE}._get_active_viewport") as mock_viewport:
            plugin._on_icon_clicked(1, True, model, item)  # button=1

        # Assert
        mock_viewport.return_value.frame_viewport_selection.assert_not_called()

    async def test_on_icon_clicked_disabled_should_not_call_frame_method(self):
        # Arrange
        plugin = self._make_plugin()
        item = self._make_item()
        model = Mock()

        # Act
        with patch(f"{_MODULE}._get_active_viewport") as mock_viewport:
            plugin._on_icon_clicked(0, False, model, item)  # enabled=False

        # Assert
        mock_viewport.return_value.frame_viewport_selection.assert_not_called()

    # ------------------------------------------------------------------
    # Group 2 — _item_clicked must NOT be called
    # ------------------------------------------------------------------

    async def test_on_icon_clicked_should_not_call_item_clicked(self):
        # Arrange
        plugin = self._make_plugin()
        item = self._make_item("/World/D")
        model = self._make_model(selected_paths=[])

        with (
            patch(f"{_MODULE}._get_active_viewport"),
            patch.object(plugin, "_item_clicked") as mock_item_clicked,
        ):
            # Act
            plugin._on_icon_clicked(0, True, model, item)

        # Assert
        mock_item_clicked.assert_not_called()

    # ------------------------------------------------------------------
    # Group 3 — path resolution via _get_action_paths
    # ------------------------------------------------------------------

    async def test_on_icon_clicked_selected_item_should_frame_full_selection(self):
        # Arrange: item A IS in the current selection [A, B, C].
        # The viewport should frame all selected prims.
        plugin = self._make_plugin()
        item = self._make_item("/World/A")
        model = self._make_model(selected_paths=["/World/A", "/World/B", "/World/C"])

        with patch(f"{_MODULE}._get_active_viewport") as mock_viewport:
            # Act
            plugin._on_icon_clicked(0, True, model, item)

        # Assert: full selection framed
        framed_paths = set(mock_viewport.return_value.frame_viewport_selection.call_args.args[0])
        self.assertEqual(framed_paths, {"/World/A", "/World/B", "/World/C"})

    async def test_on_icon_clicked_unselected_item_should_frame_only_clicked_item(self):
        # Arrange: item D is NOT in the current selection [A, B, C].
        # Consistent with other action widgets, clicking an unselected item acts on that item alone.
        plugin = self._make_plugin()
        item = self._make_item("/World/D")
        model = self._make_model(selected_paths=["/World/A", "/World/B", "/World/C"])

        with patch(f"{_MODULE}._get_active_viewport") as mock_viewport:
            # Act
            plugin._on_icon_clicked(0, True, model, item)

        # Assert: only the clicked item framed
        framed_paths = set(mock_viewport.return_value.frame_viewport_selection.call_args.args[0])
        self.assertEqual(framed_paths, {"/World/D"})

    # ------------------------------------------------------------------
    # Group 4 — _on_frame_on_the_viewport classmethod behavior
    # ------------------------------------------------------------------

    async def test_on_frame_on_the_viewport_always_uses_usd_selection(self):
        # Arrange: even if a "paths" key exists in the payload (legacy), it is ignored.
        usd_selection = ["/World/A", "/World/B"]
        payload = {"context_name": "", "paths": ["/World/D"]}

        with patch(f"{_MODULE}.usd") as mock_usd, patch(f"{_MODULE}._get_active_viewport") as mock_viewport:
            mock_usd.get_context.return_value.get_selection.return_value.get_selected_prim_paths.return_value = (
                usd_selection
            )

            # Act
            FocusInViewportActionWidgetPlugin._on_frame_on_the_viewport(payload)

        # Assert: USD selection used, payload paths ignored
        mock_viewport.return_value.frame_viewport_selection.assert_called_once_with(usd_selection)

    async def test_on_frame_on_the_viewport_missing_context_logs_error_and_returns(self):
        # Arrange
        payload = {"context_name": "missing_ctx"}

        with (
            patch(f"{_MODULE}.usd") as mock_usd,
            patch(f"{_MODULE}.carb") as mock_carb,
            patch(f"{_MODULE}._get_active_viewport") as mock_viewport,
        ):
            mock_usd.get_context.return_value = None  # no context found

            # Act
            FocusInViewportActionWidgetPlugin._on_frame_on_the_viewport(payload)

        # Assert
        mock_carb.log_error.assert_called_once()
        mock_viewport.return_value.frame_viewport_selection.assert_not_called()
