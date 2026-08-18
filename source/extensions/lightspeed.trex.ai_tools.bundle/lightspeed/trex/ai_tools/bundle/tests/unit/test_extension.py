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

import asyncio
from unittest.mock import patch

from lightspeed.trex.ai_tools.bundle.extension import AIToolsBundleExtension
from omni.kit.test import AsyncTestCase


class TestAIToolsBundleExtension(AsyncTestCase):
    """Test the AI Tools bundle extension lifecycle and sidebar behavior."""

    async def test_startup_does_not_register_standalone_app_ready_behavior(self):
        """The bundle registers full-app UI without standalone-app startup behavior."""
        # Arrange
        extension = AIToolsBundleExtension()

        with patch.object(extension, "_register_sidebar_items") as register_sidebar_items:
            # Act
            extension.on_startup("lightspeed.trex.ai_tools.bundle")

        # Assert
        register_sidebar_items.assert_called_once_with()

    async def test_shutdown_retains_layout_task_until_cancellation_settles(self):
        """Shutdown retains the layout task until its owner coroutine releases it."""
        # Arrange
        extension = AIToolsBundleExtension()
        started = asyncio.Event()

        async def wait_for_cancellation():
            """Block until the test cancels the layout-load task."""
            started.set()
            await asyncio.Event().wait()

        layout_task = asyncio.create_task(wait_for_cancellation())
        with (
            patch(
                "lightspeed.trex.ai_tools.bundle.extension.get_quicklayout_config",
                return_value="texturecraft_default_layout.json",
            ),
            patch("lightspeed.trex.ai_tools.bundle.extension.load_layout", return_value=layout_task),
        ):
            extension._load_ai_tools_layout()
            await started.wait()

            # Act
            extension.on_shutdown()

            # Assert
            self.assertIs(extension._layout_task, layout_task)
            await asyncio.gather(layout_task, return_exceptions=True)
            await asyncio.sleep(0)
        self.assertIsNone(extension._layout_task)

    async def test_layout_failure_is_logged_and_released(self):
        """A failed shared layout task reports the failure and releases extension ownership."""
        # Arrange
        extension = AIToolsBundleExtension()
        layout_task = asyncio.get_running_loop().create_future()

        with (
            patch(
                "lightspeed.trex.ai_tools.bundle.extension.get_quicklayout_config",
                return_value="texturecraft_default_layout.json",
            ),
            patch("lightspeed.trex.ai_tools.bundle.extension.load_layout", return_value=layout_task),
            patch("lightspeed.trex.ai_tools.bundle.extension.carb.log_error") as log_error,
        ):
            # Act
            extension._load_ai_tools_layout()
            layout_task.set_exception(RuntimeError("invalid layout"))
            await asyncio.sleep(0)

        # Assert
        log_error.assert_called_once_with("Failed to load the AI Tools layout: invalid layout")
        self.assertIsNone(extension._layout_task)
