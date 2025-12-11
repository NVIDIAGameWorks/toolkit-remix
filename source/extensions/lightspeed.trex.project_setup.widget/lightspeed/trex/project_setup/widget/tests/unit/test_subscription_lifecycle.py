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
from lightspeed.trex.project_setup.widget.setup_ui import ProjectSetupPane
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


class TestProjectSetupPaneSubscriptionLifecycle(AsyncTestCase):
    """Test that ProjectSetupPane properly creates/destroys subscriptions based on show() visibility."""

    async def setUp(self):
        await arrange_windows()

    async def test_subscriptions_none_initially(self):
        """Test that subscriptions are None when widget is created."""
        window = ui.Window("test_subscriptions", width=600, height=800)
        with window.frame:
            widget = ProjectSetupPane("")
        await omni.kit.app.get_app().next_update_async()

        # Subscriptions should be None initially (created in show(True))
        self.assertIsNone(widget._sub_stage_event)  # noqa: PLW0212
        self.assertIsNone(widget._sub_layer_event)  # noqa: PLW0212

        widget.destroy()
        window.destroy()

    async def test_subscriptions_created_when_shown(self):
        """Test that subscriptions are created when show(True) is called."""
        window = ui.Window("test_subscriptions", width=600, height=800)
        with window.frame:
            widget = ProjectSetupPane("")
        await omni.kit.app.get_app().next_update_async()

        # Call show(True) to create subscriptions
        widget.show(True)
        await omni.kit.app.get_app().next_update_async()

        self.assertIsNotNone(widget._sub_stage_event)  # noqa: PLW0212
        self.assertIsNotNone(widget._sub_layer_event)  # noqa: PLW0212

        widget.destroy()
        window.destroy()

    async def test_subscriptions_destroyed_when_hidden(self):
        """Test that subscriptions are destroyed when show(False) is called."""
        window = ui.Window("test_subscriptions", width=600, height=800)
        with window.frame:
            widget = ProjectSetupPane("")
        await omni.kit.app.get_app().next_update_async()

        # First show
        widget.show(True)
        await omni.kit.app.get_app().next_update_async()
        self.assertIsNotNone(widget._sub_stage_event)  # noqa: PLW0212

        # Then hide
        widget.show(False)
        await omni.kit.app.get_app().next_update_async()

        self.assertIsNone(widget._sub_stage_event)  # noqa: PLW0212
        self.assertIsNone(widget._sub_layer_event)  # noqa: PLW0212

        widget.destroy()
        window.destroy()
