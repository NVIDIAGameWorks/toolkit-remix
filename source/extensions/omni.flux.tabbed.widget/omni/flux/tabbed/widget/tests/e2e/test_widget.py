"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import omni.ui as ui
from omni.flux.tabbed.widget import SetupUI as _TabbedFrame
from omni.kit import ui_test
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


class TestTabbedWidget(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()

    # After running each test
    async def tearDown(self):
        pass

    async def __setup_widget(self, name, horizontal):
        window = ui.Window(f"TestTabbedWidgetUI{name}_{horizontal}", height=800, width=800)
        with window.frame:
            wid = _TabbedFrame(horizontal=horizontal)

        await ui_test.human_delay(human_delay_speed=1)

        return window, wid

    async def __destroy_setup(self, window, wid):
        await ui_test.human_delay(human_delay_speed=1)
        wid.destroy()
        window.frame.clear()
        window.destroy()
        await ui_test.human_delay(human_delay_speed=1)

    async def test_add_tree_tabs(self):
        # setup
        for horizontal in [True, False]:
            with self.subTest(name=f"Tab is horizontal: {horizontal}"):
                window, _wid = await self.__setup_widget("test_add_tree_tabs", horizontal)  # Keep in memory during test

                _wid.add(["Tab1", "Tab2", "Tab3"])

                # we should see 3 tabs
                tab_labels = ui_test.find_all(f"{window.title}//Frame/**/VStack[*].identifier=='TabLabel'")
                self.assertEqual(len(tab_labels), 3)
                await self.__destroy_setup(window, _wid)

    async def test_add_and_remove_tabs(self):
        # setup
        for horizontal in [True, False]:
            with self.subTest(name=f"Tab is horizontal: {horizontal}"):
                window, _wid = await self.__setup_widget("test_add_tree_tabs", horizontal)  # Keep in memory during test

                _wid.add(["Tab1", "Tab2", "Tab3"])

                # we should see 3 tabs
                tab_labels = ui_test.find_all(f"{window.title}//Frame/**/VStack[*].identifier=='TabLabel'")
                self.assertEqual(len(tab_labels), 3)

                _wid.remove(["Tab2", "Tab3"])
                tab_labels = ui_test.find_all(f"{window.title}//Frame/**/VStack[*].identifier=='TabLabel'")
                self.assertEqual(len(tab_labels), 1)

                await self.__destroy_setup(window, _wid)

    async def test_first_tab_selected_by_default(self):
        # setup
        for horizontal in [True, False]:
            with self.subTest(name=f"Tab is horizontal: {horizontal}"):
                window, _wid = await self.__setup_widget(
                    "test_first_tab_selected_by_default", horizontal
                )  # Keep in memory during test

                _wid.add(["Tab1", "Tab2", "Tab3"])

                for i, (_title, frame) in enumerate(_wid.get_frames().items()):
                    with frame:
                        ui.Label(f"TestLabel_{i}")

                # the first tab should be selected
                tab_gradients = ui_test.find_all(
                    f"{window.title}//Frame/**/ImageWithProvider[*].identifier=='SelectedGradient'"
                )
                self.assertEqual(len(tab_gradients), 3)
                self.assertTrue(tab_gradients[0].widget.visible)
                self.assertFalse(tab_gradients[1].widget.visible)
                self.assertFalse(tab_gradients[2].widget.visible)

                # first frame should be seen
                self.assertTrue(_wid.get_frame("Tab1").visible)
                self.assertFalse(_wid.get_frame("Tab2").visible)
                self.assertFalse(_wid.get_frame("Tab3").visible)

                await self.__destroy_setup(window, _wid)

    async def test_selecting_second_tab(self):
        # setup
        for horizontal in [True, False]:
            with self.subTest(name=f"Tab is horizontal: {horizontal}"):
                window, _wid = await self.__setup_widget(
                    "test_selecting_second_tab", horizontal
                )  # Keep in memory during test

                _wid.add(["Tab1", "Tab2", "Tab3"])

                for i, (_title, frame) in enumerate(_wid.get_frames().items()):
                    with frame:
                        ui.Label(f"TestLabel_{i}")

                tab_gradients = ui_test.find_all(
                    f"{window.title}//Frame/**/ImageWithProvider[*].identifier=='SelectedGradient'"
                )
                self.assertEqual(len(tab_gradients), 3)
                # select the second tab. Gradient should be seen on the second tab

                await tab_gradients[1].click()

                self.assertFalse(tab_gradients[0].widget.visible)
                self.assertTrue(tab_gradients[1].widget.visible)
                self.assertFalse(tab_gradients[2].widget.visible)

                self.assertFalse(_wid.get_frame("Tab1").visible)
                self.assertTrue(_wid.get_frame("Tab2").visible)
                self.assertFalse(_wid.get_frame("Tab3").visible)

                await self.__destroy_setup(window, _wid)

    async def test_toggle_tabs(self):
        # setup
        for horizontal in [True, False]:
            with self.subTest(name=f"Tab is horizontal: {horizontal}"):
                window, _wid = await self.__setup_widget("test_toggle_tabs", horizontal)  # Keep in memory during test

                _wid.add(["Tab1", "Tab2", "Tab3"])

                for i, (_title, frame) in enumerate(_wid.get_frames().items()):
                    with frame:
                        ui.Label(f"TestLabel_{i}")

                tab_labels = ui_test.find_all(f"{window.title}//Frame/**/VStack[*].identifier=='TabLabel'")
                work_frame = ui_test.find(f"{window.title}//Frame/**/Frame[*].identifier=='WorkFrame'")
                self.assertIsNotNone(work_frame)

                # by default, the first frame is visible
                self.assertTrue(work_frame.widget.visible)
                await tab_labels[0].click()
                # it should toggle the first frame. So it should not be visible anymore
                self.assertFalse(work_frame.widget.visible)
                # toggle again
                await tab_labels[0].click()
                self.assertTrue(work_frame.widget.visible)

                # switch tab
                await tab_labels[1].click()
                self.assertTrue(work_frame.widget.visible)
                # toggle
                await tab_labels[1].click()
                self.assertFalse(work_frame.widget.visible)

                # switch tab
                await tab_labels[2].click()
                self.assertFalse(work_frame.widget.visible)

                await self.__destroy_setup(window, _wid)
