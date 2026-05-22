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

import omni.kit.app
from omni.flux.utils.dialog import ProgressPopup
from omni.kit.test import AsyncTestCase


class TestProgressPopup(AsyncTestCase):
    async def test_cancel_disabled_should_keep_popup_visible_and_skip_callback(self):
        popup = ProgressPopup(title="Test Progress")
        cancel_count = 0

        def cancel():
            nonlocal cancel_count
            cancel_count += 1

        try:
            popup.set_cancel_fn(cancel)
            popup.show()

            popup.set_cancel_enabled(False)
            await omni.kit.app.get_app().next_update_async()
            popup._on_cancel_button_fn()

            self.assertTrue(popup.is_visible())
            self.assertFalse(popup._buttons[0].enabled)
            self.assertEqual(0, cancel_count)

            popup.set_cancel_enabled(True)
            popup._on_cancel_button_fn()

            self.assertFalse(popup.is_visible())
            self.assertTrue(popup._buttons[0].enabled)
            self.assertEqual(1, cancel_count)
        finally:
            popup.destroy()

    async def test_progress_and_status_properties_should_update_popup(self):
        popup = ProgressPopup(title="Test Progress", status_text="Starting")

        try:
            with popup:
                popup.progress = 0.25
                popup.status_text = "Working"

                self.assertTrue(popup.is_visible())
                self.assertEqual(0.25, popup.progress)
                self.assertEqual("25%", popup._progress_bar_model.get_value_as_string())
                self.assertEqual("Working", popup.status_text)

            self.assertFalse(popup.is_visible())
        finally:
            popup.destroy()
