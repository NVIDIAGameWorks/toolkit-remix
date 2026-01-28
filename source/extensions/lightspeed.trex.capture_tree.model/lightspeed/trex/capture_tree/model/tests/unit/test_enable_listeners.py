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

from lightspeed.trex.capture_tree.model import CaptureTreeModel
from omni.kit.test import AsyncTestCase


class TestCaptureTreeModelEnableListeners(AsyncTestCase):
    """Test that CaptureTreeModel.enable_listeners() properly creates/destroys subscriptions."""

    async def test_subscriptions_none_by_default(self):
        """Test that subscriptions are None when model is created."""
        model = CaptureTreeModel("")

        self.assertIsNone(model._stage_event_sub)  # noqa: SLF001
        self.assertIsNone(model._layer_event_sub)  # noqa: SLF001

        model.destroy()

    async def test_subscriptions_created_when_enabled(self):
        """Test that subscriptions are created when enable_listeners(True) is called."""
        model = CaptureTreeModel("")

        model.enable_listeners(True)

        self.assertIsNotNone(model._stage_event_sub)  # noqa: SLF001
        self.assertIsNotNone(model._layer_event_sub)  # noqa: SLF001

        model.enable_listeners(False)
        model.destroy()

    async def test_subscriptions_destroyed_when_disabled(self):
        """Test that subscriptions are destroyed when enable_listeners(False) is called."""
        model = CaptureTreeModel("")

        # First enable
        model.enable_listeners(True)
        self.assertIsNotNone(model._stage_event_sub)  # noqa: SLF001
        self.assertIsNotNone(model._layer_event_sub)  # noqa: SLF001

        # Then disable
        model.enable_listeners(False)
        self.assertIsNone(model._stage_event_sub)  # noqa: SLF001
        self.assertIsNone(model._layer_event_sub)  # noqa: SLF001

        model.destroy()

    async def test_subscriptions_toggle_multiple_times(self):
        """Test that subscriptions can be toggled on/off multiple times."""
        model = CaptureTreeModel("")

        # Toggle on
        model.enable_listeners(True)
        self.assertIsNotNone(model._stage_event_sub)  # noqa: SLF001
        self.assertIsNotNone(model._layer_event_sub)  # noqa: SLF001

        # Toggle off
        model.enable_listeners(False)
        self.assertIsNone(model._stage_event_sub)  # noqa: SLF001
        self.assertIsNone(model._layer_event_sub)  # noqa: SLF001

        # Toggle on again
        model.enable_listeners(True)
        self.assertIsNotNone(model._stage_event_sub)  # noqa: SLF001
        self.assertIsNotNone(model._layer_event_sub)  # noqa: SLF001

        # Toggle off again
        model.enable_listeners(False)
        self.assertIsNone(model._stage_event_sub)  # noqa: SLF001
        self.assertIsNone(model._layer_event_sub)  # noqa: SLF001

        model.destroy()
