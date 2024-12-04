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
from lightspeed.trex.capture_tree.model import CaptureTreeDelegate as _CaptureTreeDelegate
from lightspeed.trex.capture_tree.model import CaptureTreeModel as _CaptureTreeModel
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, open_stage, wait_stage_loading


class TestTreeWidget(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await arrange_windows()
        await open_stage(_get_test_data("usd/project_example/combined.usda"))

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()

    async def __setup_widget(self):
        window = ui.Window("TestTreeUI", height=800, width=400)
        capture_model = _CaptureTreeModel("", show_progress=False)
        capture_model.refresh(
            [
                (
                    _get_test_data("usd/project_example/.deps/captures/capture.usda"),
                    _get_test_data("usd/project_example/.deps/captures/.thumbs/capture.usda.dds"),
                ),
                (_get_test_data("usd/project_example/.deps/captures/capture.usda"), None),
            ]
        )
        capture_delegate = _CaptureTreeDelegate()
        with window.frame:
            ui.TreeView(
                capture_model,
                delegate=capture_delegate,
                root_visible=False,
                header_visible=False,
                columns_resizable=False,
                identifier="CaptureTree",
            )

        await ui_test.human_delay(human_delay_speed=1)

        return window

    async def test_show_big_thumbnail(self):
        # setup
        _window = await self.__setup_widget()  # Keep in memory during test

        big_window_name = "Capture image bigger"

        # we have 2 items
        items = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_title'")
        self.assertEqual(len(items), 2)

        # by default the big thumbnail is invisible
        item_images = ui_test.find_all(f"{_window.title}//Frame/**/Image[*].identifier=='item_thumbnail'")
        item_no_images = ui_test.find_all(f"{_window.title}//Frame/**/Rectangle[*].identifier=='item_no_thumbnail'")
        big_images = ui_test.find(f"{big_window_name}//Frame/**/Image[*].identifier=='big_image'")
        no_images = ui_test.find(f"{big_window_name}//Frame/**/Label[*].identifier=='no_image'")
        big_thumbnail_window = ui_test.find(big_window_name)

        self.assertFalse(big_thumbnail_window.window.visible)
        self.assertEqual(big_images.widget.source_url, "")
        self.assertFalse(no_images.widget.visible)
        self.assertEqual(len(item_images), 1)
        self.assertEqual(len(item_no_images), 1)

        # we go hover the item with a thumbnail. We should see a big image
        await ui_test.input.emulate_mouse_move(item_images[0].center)
        await ui_test.human_delay(human_delay_speed=1)

        big_thumbnail_window = ui_test.find(big_window_name)
        big_images = ui_test.find(f"{big_window_name}//Frame/**/Image[*].identifier=='big_image'")
        no_images = ui_test.find(f"{big_window_name}//Frame/**/Label[*].identifier=='no_image'")

        self.assertTrue(big_thumbnail_window.window.visible)
        self.assertEqual(
            big_images.widget.source_url, _get_test_data("usd/project_example/.deps/captures/.thumbs/capture.usda.dds")
        )
        self.assertFalse(no_images.widget.visible)

        # we go hover the item with no thumbnail. We should see a "no image"
        await ui_test.input.emulate_mouse_move(item_no_images[0].center)
        await ui_test.human_delay(human_delay_speed=1)

        no_images = ui_test.find(f"{big_window_name}//Frame/**/Label[*].identifier=='no_image'")
        self.assertTrue(no_images.widget.visible)
