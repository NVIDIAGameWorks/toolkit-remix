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

from unittest.mock import Mock

import omni.kit.app
import omni.ui as ui
from lightspeed.trex.packaging.widget.setup_ui import PackagingPane
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


async def _create_widget(window_name: str) -> tuple[ui.Window, PackagingPane]:
    window = ui.Window(window_name, width=600, height=800)
    with window.frame:
        widget = PackagingPane("")
    await omni.kit.app.get_app().next_update_async()
    return window, widget


class TestPackagingPaneProgressE2E(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()

    async def test_cancelled_packaging_should_show_disabled_cleanup_progress(self):
        window, widget = await _create_widget("test_cancelled_packaging_late_progress")

        try:
            # Show the real progress popup from a packaging progress event.
            widget._packaging_core = Mock()

            widget._on_packaging_progress(0, 1, "Filtering the selected layers...")
            await omni.kit.app.get_app().next_update_async()

            popup = widget._progress_popup
            self.assertIsNotNone(popup)
            self.assertTrue(popup.is_visible())

            # Click Cancel and verify the popup immediately shows the disabled cancellation state.
            popup._on_cancel_button_fn()
            await omni.kit.app.get_app().next_update_async()

            widget._packaging_core.cancel.assert_called_once()
            self.assertTrue(widget._packaging_cancel_requested)
            self.assertTrue(popup.is_visible())
            self.assertEqual("Cancelling packaging...", popup.status_text)
            self.assertEqual(0.5, popup.progress)

            # Click Cancel again to confirm the disabled button no longer forwards cancellation.
            popup._on_cancel_button_fn()
            await omni.kit.app.get_app().next_update_async()

            widget._packaging_core.cancel.assert_called_once()
            self.assertTrue(popup.is_visible())

            # Send the normal cleanup progress event and verify the same popup stays visible with Cancel disabled.
            widget._on_packaging_progress(1, 1, "Cleaning up temporary layers...")
            await omni.kit.app.get_app().next_update_async()

            self.assertTrue(popup.is_visible())
            self.assertEqual("Cleaning up temporary layers...\n1 / 1", popup.status_text)
            self.assertEqual(1, popup.progress)

            # Click Cancel during cleanup to make sure cleanup cannot be interrupted through the dialog.
            popup._on_cancel_button_fn()
            await omni.kit.app.get_app().next_update_async()

            widget._packaging_core.cancel.assert_called_once()
            self.assertTrue(popup.is_visible())
        finally:
            widget.destroy()
            window.destroy()
