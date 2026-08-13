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

import omni.kit.test
import omni.ui as ui
from omni.flux.utils.widget.collapsable_frame import (
    PropertyCollapsableFrame,
    PropertyCollapsableFrameAction,
    PropertyCollapsableFrameWithInfoPopup,
)
from omni.kit import ui_test


class TestPropertyCollapsableFrame(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._window = ui.Window(
            "TestPropertyCollapsableFrame",
            height=200,
            width=600,
            position_x=0,
            position_y=0,
        )
        self._frame = None
        self._action_click_count = 0

    async def tearDown(self):
        if self._frame:
            self._frame.destroy()
            self._frame = None
        if self._window:
            self._window.destroy()
            self._window = None

    async def _wait_for_ui(self, update_count=3):
        for _ in range(update_count):
            await ui_test.human_delay(human_delay_speed=1)

    def _build_frame(self, collapsed=False, with_info_popup=False):
        def _action_clicked():
            self._action_click_count += 1

        with self._window.frame:
            frame_cls = PropertyCollapsableFrameWithInfoPopup if with_info_popup else PropertyCollapsableFrame
            kwargs = {"info_text": "Section details"} if with_info_popup else {}
            self._frame = frame_cls(
                "TEST SECTION",
                collapsed=collapsed,
                pinnable=True,
                pinned_text_fn=lambda: "Pinned selection",
                actions=[
                    PropertyCollapsableFrameAction(
                        name="More",
                        clicked_fn=_action_clicked,
                        identifier="property_frame_test_action",
                    )
                ],
                **kwargs,
            )
            with self._frame:
                ui.Label("Frame body", identifier="property_frame_body")

    def _find_header_title(self):
        titles = ui_test.find_all(f"{self._window.title}//Frame/**/Label[*].name=='PropertiesPaneSectionTitle'")
        self.assertEqual(len(titles), 1)
        return titles[0]

    def _find_header_arrow(self):
        arrows = ui_test.find_all(
            f"{self._window.title}//Frame/**/Image[*].identifier=='PropertyCollapsableFrameArrow'"
        )
        self.assertEqual(len(arrows), 1)
        return arrows[0]

    async def test_header_expander_icon_aligns_with_other_header_icons(self):
        self._build_frame()
        await self._wait_for_ui()

        arrow = self._find_header_arrow()
        action_icon = ui_test.find(f"{self._window.title}//Frame/**/Image[*].identifier=='property_frame_test_action'")
        pin_icon = ui_test.find(f"{self._window.title}//Frame/**/Image[*].identifier=='property_frame_pin_icon'")
        self.assertIsNotNone(action_icon)
        self.assertIsNotNone(pin_icon)

        self.assertAlmostEqual(arrow.center.y, action_icon.center.y, delta=1)
        self.assertAlmostEqual(arrow.center.y, pin_icon.center.y, delta=1)

    async def test_header_title_text_expands_frame_with_info_popup(self):
        self._build_frame(collapsed=True, with_info_popup=True)
        await self._wait_for_ui()

        title = self._find_header_title()

        await title.click()
        await self._wait_for_ui()

        self.assertFalse(self._frame.root.collapsed)

    async def test_header_empty_space_toggles_frame(self):
        self._build_frame()
        await self._wait_for_ui()

        title = self._find_header_title()
        arrow = self._find_header_arrow()
        empty_header_space = ui_test.Vec2((title.center.x + arrow.center.x) * 0.5, title.center.y)

        await ui_test.emulate_mouse_move_and_click(empty_header_space)
        await self._wait_for_ui()

        self.assertTrue(self._frame.root.collapsed)

    async def test_header_actions_do_not_toggle_frame(self):
        self._build_frame()
        await self._wait_for_ui()

        pin_icon = ui_test.find(f"{self._window.title}//Frame/**/Image[*].identifier=='property_frame_pin_icon'")
        action_icon = ui_test.find(f"{self._window.title}//Frame/**/Image[*].identifier=='property_frame_test_action'")
        self.assertIsNotNone(pin_icon)
        self.assertIsNotNone(action_icon)

        await pin_icon.click()
        await self._wait_for_ui()
        self.assertFalse(self._frame.root.collapsed)

        action_icon = ui_test.find(f"{self._window.title}//Frame/**/Image[*].identifier=='property_frame_test_action'")
        await action_icon.click()
        await self._wait_for_ui()

        self.assertFalse(self._frame.root.collapsed)
        self.assertEqual(self._action_click_count, 1)
