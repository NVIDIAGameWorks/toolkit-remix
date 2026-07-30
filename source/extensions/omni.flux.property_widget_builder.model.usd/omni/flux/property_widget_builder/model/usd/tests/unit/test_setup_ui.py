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
import omni.kit.test
import omni.ui as ui
from omni.flux.property_widget_builder.model.usd import USDDelegate, USDModel, USDPropertyWidget


class TestUSDPropertyWidget(omni.kit.test.AsyncTestCase):
    async def test_destroy_with_pending_expansion_update_cancels_inherited_task(self):
        # Arrange
        window = ui.Window("TestUSDPropertyWidgetPendingExpansion", width=500, height=300)
        widget = None
        try:
            with window.frame:
                widget = USDPropertyWidget(context_name="", model=USDModel(context_name=""), delegate=USDDelegate())
            widget._update_expansion_state_deferred()
            update_task = widget._update_task

            # Act
            widget.destroy()

            # Assert
            await omni.kit.app.get_app().next_update_async()
            self.assertTrue(update_task.cancelled())
        finally:
            if widget is not None and widget._root_frame is not None:
                widget.destroy()
            window.destroy()

    async def test_destroy_after_resize_releases_base_widget_state(self):
        # Arrange
        model = USDModel(context_name="")
        delegate = USDDelegate()
        window = ui.Window("TestUSDPropertyWidgetLifecycle", width=500, height=300)
        widget = None
        try:
            with window.frame:
                widget = USDPropertyWidget(
                    context_name="",
                    model=model,
                    delegate=delegate,
                    tree_column_widths=[ui.Pixel(270), ui.Fraction(1)],
                    columns_resizable=True,
                )
            window.width = 340
            for _ in range(4):
                await omni.kit.app.get_app().next_update_async()
            self.assertIsNotNone(widget._last_name_column_width, "Expected the responsive resize callback to run")

            # Act
            widget.destroy()

            # Assert
            self.assertIsNone(widget._root_frame)
            self.assertIsNone(widget._tree_view)
            self.assertIsNone(widget._on_item_expanded_sub)
            self.assertIsNone(widget._on_item_changed_sub)
            self.assertIsNone(widget._on_attribute_created_sub)
            self.assertIsNone(widget._last_name_column_width)
        finally:
            if widget is not None and widget._root_frame is not None:
                widget.destroy()
            window.destroy()
