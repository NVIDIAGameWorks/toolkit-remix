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

__all__ = ("TestIntDragFieldGroup",)

import uuid

import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from omni.flux.property_widget_builder.delegates.int_value.drag import IntDragFieldGroup

from .mocks import MockItem


class TestIntDragFieldGroup(omni.kit.test.AsyncTestCase):
    """E2E tests for IntDragFieldGroup widget rendering."""

    async def test_build_drag_widget_creates_int_drag(self):
        """build_ui should produce ui.IntDrag widgets."""
        window = ui.Window(
            f"TestIntDrag_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[25])
        field = IntDragFieldGroup(min_value=0, max_value=100)

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertEqual(len(widgets), 1)
        self.assertIsInstance(widgets[0], ui.IntDrag)

        for w in widgets:
            w.destroy()
        window.destroy()

    async def test_build_unbounded_creates_int_drag(self):
        """build_ui with no bounds should still produce a ui.IntDrag."""
        window = ui.Window(
            f"TestIntDrag_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        item = MockItem(values=[25])
        field = IntDragFieldGroup()

        with window.frame:
            widgets = field.build_ui(item)

        await omni.kit.ui_test.human_delay(human_delay_speed=1)

        self.assertEqual(len(widgets), 1)
        self.assertIsInstance(widgets[0], ui.IntDrag)

        for w in widgets:
            w.destroy()
        window.destroy()
