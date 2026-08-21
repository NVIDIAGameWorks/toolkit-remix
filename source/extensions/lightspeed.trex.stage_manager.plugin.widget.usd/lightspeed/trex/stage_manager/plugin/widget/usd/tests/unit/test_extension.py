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

__all__ = ["TestLightspeedStageManagerUSDWidgetPluginsExtension"]

from unittest.mock import MagicMock, patch

import omni.kit.test
from lightspeed.common.constants import GlobalEventNames

from ...extension import LightspeedStageManagerUSDWidgetPluginsExtension

_DELETE_CONTROLLER = "lightspeed.trex.stage_manager.plugin.widget.usd.extension._DeleteRestoreActionWidgetPlugin"
_EVENT_MANAGER = "lightspeed.trex.stage_manager.plugin.widget.usd.extension._get_event_manager_instance"
_FACTORY = "lightspeed.trex.stage_manager.plugin.widget.usd.extension._get_factory_instance"


class TestLightspeedStageManagerUSDWidgetPluginsExtension(omni.kit.test.AsyncTestCase):
    """Test viewport deletion event wiring owned by the extension."""

    async def test_startup_with_event_manager_subscribes_viewport_delete_request(self):
        """Startup subscribes the viewport deletion callback to the global event."""
        # Arrange
        extension = LightspeedStageManagerUSDWidgetPluginsExtension()
        event_manager = MagicMock()

        with (
            patch(_EVENT_MANAGER, return_value=event_manager),
            patch(_DELETE_CONTROLLER),
            patch(_FACTORY),
        ):
            # Act
            extension.on_startup("test_extension")

        # Assert
        event_manager.subscribe_global_custom_event.assert_called_once_with(
            GlobalEventNames.VIEWPORT_DELETE_SELECTION_REQUEST.value,
            extension._on_viewport_delete_selection_requested,
        )

    async def test_viewport_delete_request_with_context_deletes_selection_in_requested_context(self):
        """A viewport request deletes the selection in its explicit USD context."""
        # Arrange
        extension = LightspeedStageManagerUSDWidgetPluginsExtension()
        controller = MagicMock()
        extension._delete_controller = controller

        # Act
        extension._on_viewport_delete_selection_requested("viewport_context")

        # Assert
        controller.set_context_name.assert_called_once_with("viewport_context")
        controller.delete_selected_prims.assert_called_once_with(notify_ineligible=True)

    async def test_shutdown_releases_viewport_delete_resources(self):
        """Shutdown releases viewport deletion resources and unregisters plugins."""
        # Arrange
        extension = LightspeedStageManagerUSDWidgetPluginsExtension()
        extension._delete_controller = MagicMock()
        extension._viewport_delete_subscription = MagicMock()

        # Act
        with patch(_FACTORY) as factory:
            extension.on_shutdown()

        # Assert
        self.assertIsNone(extension._viewport_delete_subscription)
        self.assertIsNone(extension._delete_controller)
        factory.return_value.unregister_plugins.assert_called_once_with(extension._PLUGINS)
