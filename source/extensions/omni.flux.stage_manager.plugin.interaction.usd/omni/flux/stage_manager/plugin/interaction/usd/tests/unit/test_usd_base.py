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

from types import SimpleNamespace
from unittest import mock

from omni.kit.test import AsyncTestCase
from omni.flux.stage_manager.factory.plugins.interaction_plugin import (
    StageManagerInteractionPlugin as _StageManagerInteractionPlugin,
)
from omni.flux.stage_manager.plugin.interaction.usd.base import (
    StageManagerUSDInteractionPlugin as _StageManagerUSDInteractionPlugin,
)


class _TestInteractionPlugin(_StageManagerUSDInteractionPlugin):
    pass


class TestStageManagerUSDInteractionPlugin(AsyncTestCase):
    async def test_on_selection_changed_does_not_write_back_for_order_only_difference(self):
        # Arrange
        plugin = _TestInteractionPlugin.model_construct(
            tree=mock.MagicMock(),
            filters=[],
            context_filters=[],
            internal_context_filters=[],
            columns=[],
            additional_filters=[],
            compatible_filters=[],
            compatible_widgets=[],
            compatible_trees=[],
        )
        plugin._selection_update_lock = False
        plugin.synchronize_selection = True
        plugin._ignore_selection_update = False
        plugin._context_name = ""

        items = [
            SimpleNamespace(data=SimpleNamespace(GetPath=lambda: "/World/B")),
            SimpleNamespace(data=SimpleNamespace(GetPath=lambda: "/World/A")),
        ]

        with (
            mock.patch.object(_StageManagerInteractionPlugin, "_on_selection_changed", autospec=True) as super_sel,
            mock.patch.object(plugin, "_get_selection", return_value=["/World/A", "/World/B"]),
            mock.patch("omni.usd.get_context") as get_context,
        ):
            selection_mock = mock.MagicMock()
            context_mock = mock.MagicMock(get_selection=mock.MagicMock(return_value=selection_mock))
            get_context.return_value = context_mock

            # Act
            plugin._on_selection_changed(items)

            # Assert
            super_sel.assert_called_once()
            selection_mock.set_selected_prim_paths.assert_not_called()

    async def test_on_selection_changed_writes_back_when_selected_set_changes(self):
        # Arrange
        plugin = _TestInteractionPlugin.model_construct(
            tree=mock.MagicMock(),
            filters=[],
            context_filters=[],
            internal_context_filters=[],
            columns=[],
            additional_filters=[],
            compatible_filters=[],
            compatible_widgets=[],
            compatible_trees=[],
        )
        plugin._selection_update_lock = False
        plugin.synchronize_selection = True
        plugin._ignore_selection_update = False
        plugin._context_name = ""

        items = [
            SimpleNamespace(data=SimpleNamespace(GetPath=lambda: "/World/A")),
            SimpleNamespace(data=SimpleNamespace(GetPath=lambda: "/World/C")),
        ]

        with (
            mock.patch.object(_StageManagerInteractionPlugin, "_on_selection_changed", autospec=True) as super_sel,
            mock.patch.object(plugin, "_get_selection", return_value=["/World/A", "/World/B"]),
            mock.patch("omni.usd.get_context") as get_context,
        ):
            selection_mock = mock.MagicMock()
            context_mock = mock.MagicMock(get_selection=mock.MagicMock(return_value=selection_mock))
            get_context.return_value = context_mock

            # Act
            plugin._on_selection_changed(items)

            # Assert
            super_sel.assert_called_once()
            selection_mock.set_selected_prim_paths.assert_called_once_with(["/World/A", "/World/C"])
