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
from lightspeed.trex.capture_tree.widget.setup_ui import CaptureWidget
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


class TestCaptureWidgetSubscriptionLifecycle(AsyncTestCase):
    """Test that CaptureWidget properly manages subscriptions and model listeners."""

    async def setUp(self):
        await arrange_windows()

    async def test_subscriptions_created_in_init(self):
        """Test that widget subscriptions to model events are created in __init__."""
        window = ui.Window("test_subscriptions", width=600, height=800)
        with window.frame:
            widget = CaptureWidget("")
        await omni.kit.app.get_app().next_update_async()

        # Widget subscribes to model events in __init__
        self.assertIsNotNone(widget._sub_model_changed)  # noqa: SLF001
        self.assertIsNotNone(widget._sub_stage_event)  # noqa: SLF001
        self.assertIsNotNone(widget._sub_layer_event)  # noqa: SLF001

        window.destroy()

    async def test_model_listeners_enabled_when_shown(self):
        """Test that model.enable_listeners(True) is called when show(True) is called."""
        window = ui.Window("test_subscriptions", width=600, height=800)
        with window.frame:
            widget = CaptureWidget("")
        await omni.kit.app.get_app().next_update_async()

        # Model listeners should be disabled initially
        self.assertIsNone(widget._capture_tree_model._stage_event_sub)  # noqa: SLF001
        self.assertIsNone(widget._capture_tree_model._layer_event_sub)  # noqa: SLF001

        # Call show(True) to enable model listeners
        widget.show(True)
        await omni.kit.app.get_app().next_update_async()

        self.assertIsNotNone(widget._capture_tree_model._stage_event_sub)  # noqa: SLF001
        self.assertIsNotNone(widget._capture_tree_model._layer_event_sub)  # noqa: SLF001

        window.destroy()

    async def test_model_listeners_disabled_when_hidden(self):
        """Test that model.enable_listeners(False) is called when show(False) is called."""
        window = ui.Window("test_subscriptions", width=600, height=800)
        with window.frame:
            widget = CaptureWidget("")
        await omni.kit.app.get_app().next_update_async()

        # First show to enable
        widget.show(True)
        await omni.kit.app.get_app().next_update_async()
        self.assertIsNotNone(widget._capture_tree_model._stage_event_sub)  # noqa: SLF001

        # Then hide to disable
        widget.show(False)
        await omni.kit.app.get_app().next_update_async()

        self.assertIsNone(widget._capture_tree_model._stage_event_sub)  # noqa: SLF001
        self.assertIsNone(widget._capture_tree_model._layer_event_sub)  # noqa: SLF001

        window.destroy()

    async def test_model_listeners_toggle_multiple_times(self):
        """Test that model listeners can be toggled on/off multiple times."""
        window = ui.Window("test_subscriptions", width=600, height=800)
        with window.frame:
            widget = CaptureWidget("")
        await omni.kit.app.get_app().next_update_async()

        # Toggle on
        widget.show(True)
        await omni.kit.app.get_app().next_update_async()
        self.assertIsNotNone(widget._capture_tree_model._stage_event_sub)  # noqa: SLF001

        # Toggle off
        widget.show(False)
        await omni.kit.app.get_app().next_update_async()
        self.assertIsNone(widget._capture_tree_model._stage_event_sub)  # noqa: SLF001

        # Toggle on again
        widget.show(True)
        await omni.kit.app.get_app().next_update_async()
        self.assertIsNotNone(widget._capture_tree_model._stage_event_sub)  # noqa: SLF001

        window.destroy()
