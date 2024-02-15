"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import contextlib
import shutil
import tempfile

import omni.ui as ui
import omni.usd
from lightspeed.trex.properties_pane.shared.mod_setup.widget import ModSetupPane as _ModSetupPane
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, open_stage, wait_stage_loading


@contextlib.asynccontextmanager
async def make_temp_directory(context):
    temp_dir = tempfile.TemporaryDirectory()  # noqa PLR1732
    try:
        yield temp_dir
    finally:
        if context.can_close_stage():
            await context.close_stage_async()
        temp_dir.cleanup()


class TestModSetupWidget(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await arrange_windows()

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()

    async def __setup_widget(self, title: str):
        window = ui.Window(title, height=800, width=400)
        with window.frame:
            wid = _ModSetupPane("")
            wid.show(True)

        await ui_test.human_delay(human_delay_speed=1)

        return window, wid

    async def __destroy(self, window, wid):
        wid.destroy()
        window.destroy()

    async def test_capture_item_centered(self):
        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            # setup
            shutil.copytree(_get_test_data("usd/project_example"), f"{temp_dir.name}/project_example")
            # we duplicate a lot of capture to have the current one in the middle of the list
            number_captures = 20
            chars = ["a", "d"]
            for char in chars:
                for i in range(number_captures):
                    shutil.copy(
                        _get_test_data("usd/project_example/.deps/captures/capture.usda"),
                        f"{temp_dir.name}/project_example/.deps/captures/{char}_capture{i}.usda",
                    )

            await open_stage(f"{temp_dir.name}/project_example/combined.usda")
            _window, _wid = await self.__setup_widget("test_capture_item_centered")  # Keep in memory during test

            await ui_test.human_delay(human_delay_speed=10)

            tree_capture_scroll_frame = ui_test.find(
                f"{_window.title}//Frame/**/ScrollingFrame[*].identifier=='TreeCaptureScrollFrame'"
            )
            items = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_title'")
            self.assertIsNotNone(tree_capture_scroll_frame)
            self.assertEqual(len(items), (number_captures * len(chars)) + 1)

            # 2 pixels delta
            header_offset = 12
            self.assertTrue(
                tree_capture_scroll_frame.center.y - 2
                < items[number_captures].center.y - header_offset
                < tree_capture_scroll_frame.center.y + 2
            )

            await self.__destroy(_window, _wid)
