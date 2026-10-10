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

__all__ = ["TestAlphaCutoutWidgetExtension"]

from unittest.mock import MagicMock, patch

from lightspeed.common.constants import GlobalEventNames
from lightspeed.trex.alpha_cutout.widget.extension import AlphaCutoutWidgetExtension
from omni.kit.test import AsyncTestCase

_MODULE = "lightspeed.trex.alpha_cutout.widget.extension"


class TestAlphaCutoutWidgetExtension(AsyncTestCase):
    """Test the window registration and the event routing."""

    async def test_startup_creates_window_registers_show_fn_and_subscribes_to_convert_request(self):
        # Arrange
        extension = AlphaCutoutWidgetExtension()
        window = MagicMock()
        window.title = "Convert Alpha Cards to Mesh"
        event_manager = MagicMock()

        # Act
        with (
            patch(f"{_MODULE}._AlphaCutoutWindow", return_value=window),
            patch(f"{_MODULE}._get_event_manager_instance", return_value=event_manager),
            patch(f"{_MODULE}.omni.ui.Workspace.set_show_window_fn") as set_show_window_fn,
        ):
            extension.on_startup("lightspeed.trex.alpha_cutout.widget")

        # Assert
        window.create_window.assert_called_once_with()
        set_show_window_fn.assert_called_once_with(window.title, window.show_window_fn)
        event_manager.subscribe_global_custom_event.assert_called_once_with(
            GlobalEventNames.ALPHA_CUTOUT_CONVERT_REQUEST.value, extension._on_convert_request
        )

    async def test_convert_request_opens_window_with_meshes_and_context(self):
        # Arrange
        extension = AlphaCutoutWidgetExtension()
        window = MagicMock()
        extension._window = window

        # Act
        extension._on_convert_request(("/RootNode/meshes/mesh_AAAAAAAAAAAAAAAA",), "ctx")

        # Assert
        window.open_with_meshes.assert_called_once_with(["/RootNode/meshes/mesh_AAAAAAAAAAAAAAAA"], "ctx")

    async def test_shutdown_releases_subscription_and_cleans_window(self):
        # Arrange
        extension = AlphaCutoutWidgetExtension()
        window = MagicMock()
        window.title = "Convert Alpha Cards to Mesh"
        extension._window = window
        extension._convert_request_sub = MagicMock()

        # Act
        with patch(f"{_MODULE}.omni.ui.Workspace.set_show_window_fn") as set_show_window_fn:
            extension.on_shutdown()

        # Assert
        window.cleanup.assert_called_once_with()
        set_show_window_fn.assert_called_once()
        self.assertIsNone(extension._window)
        self.assertIsNone(extension._convert_request_sub)
