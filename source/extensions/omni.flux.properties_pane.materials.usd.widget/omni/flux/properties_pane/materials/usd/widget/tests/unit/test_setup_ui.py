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
from unittest.mock import Mock, patch

from omni.flux.properties_pane.materials.usd.widget import setup_ui
from omni.kit.test import AsyncTestCase

__all__ = ("TestMaterialPropertyWidgetRefresh",)


class TestMaterialPropertyWidgetRefresh(AsyncTestCase):
    """Verify ownership of pending material refreshes."""

    async def test_pending_refresh_replacement_or_destroy_cancels_obsolete_work(self):
        """Cancel pending work before another refresh or destruction can make it obsolete."""
        for action in ("replace", "destroy"):
            with self.subTest(title=action):
                # Arrange
                entered, release = asyncio.Event(), asyncio.Event()

                async def next_update(entered=entered, release=release):
                    entered.set()
                    await release.wait()

                widget = setup_ui.MaterialPropertyWidget.__new__(setup_ui.MaterialPropertyWidget)
                widget._refresh_task = None
                widget._paths = []
                widget._context = Mock()
                widget._context.get_stage.return_value = None
                widget._root_frame = Mock(visible=True)
                widget._property_model = model = Mock()
                widget._MaterialPropertyWidget__usd_listener_instance = Mock()
                widget._refresh_done = completed = Mock()
                widget._default_attr = {
                    "_context": None,
                    "_root_frame": None,
                    "_property_model": None,
                    "_paths": None,
                }
                read_stage = widget._context.get_stage
                tasks = []

                with patch.object(setup_ui, "omni") as omni_module:
                    omni_module.kit.app.get_app.return_value.next_update_async = next_update
                    try:
                        widget.refresh(["/Old"])
                        old_task = widget._refresh_task
                        tasks.append(old_task)
                        await entered.wait()

                        # Act
                        if action == "replace":
                            widget.refresh(["/New"])
                            tasks.append(widget._refresh_task)
                        else:
                            widget.destroy()
                        cancellation_requests = old_task.cancelling()
                        release.set()
                        await asyncio.gather(*tasks, return_exceptions=True)

                        # Assert
                        self.assertGreater(cancellation_requests, 0)
                        expected_refreshes = int(action == "replace")
                        self.assertEqual(read_stage.call_count, expected_refreshes)
                        self.assertEqual(model.set_items.call_count, expected_refreshes)
                        self.assertEqual(completed.call_count, expected_refreshes)
                        if action == "destroy":
                            self.assertIsNone(widget._refresh_task)
                    finally:
                        release.set()
                        for task in tasks:
                            task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
