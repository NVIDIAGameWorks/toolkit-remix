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
from lightspeed.trex.packaging.widget.setup_ui import PackagingPane
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


class TestPackagingPaneSubscriptionLifecycle(AsyncTestCase):
    """Test that PackagingPane properly creates/destroys subscriptions based on show() visibility."""

    async def setUp(self):
        await arrange_windows()

    async def test_subscriptions_none_initially(self):
        """Test that subscriptions are None when widget is created."""
        window = ui.Window("test_subscriptions", width=600, height=800)
        with window.frame:
            widget = PackagingPane("")
        await omni.kit.app.get_app().next_update_async()

        # Subscriptions should be None initially (created in show(True))
        self.assertIsNone(widget._packaging_progress_sub)  # noqa: SLF001
        self.assertIsNone(widget._packaging_completed_sub)  # noqa: SLF001

        widget.destroy()
        window.destroy()

    # Note: show(True/False) tests require a stage to be open as child widgets
    # access layer data. Full lifecycle testing is covered by e2e tests.
