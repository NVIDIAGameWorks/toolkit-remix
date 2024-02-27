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
import os
import shutil
import tempfile

import carb.input as carb_input
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
            self.assertTrue(
                tree_capture_scroll_frame.center.y - 2
                < items[number_captures].center.y
                < tree_capture_scroll_frame.center.y + 2
            )

            await self.__destroy(_window, _wid)

    async def test_capture_list_refresh(self):
        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            # Setup
            shutil.copytree(_get_test_data("usd/project_example"), f"{temp_dir.name}/project_example")
            await open_stage(f"{temp_dir.name}/project_example/combined.usda")
            _window, _wid = await self.__setup_widget("test_capture_item_centered")  # Keep in memory during test
            await ui_test.human_delay(human_delay_speed=10)

            # Ensure there is one capture
            items = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_title'")
            self.assertEqual(len(items), 1)

            # Duplicate the capture file
            shutil.copy(
                _get_test_data("usd/project_example/.deps/captures/capture.usda"),
                f"{temp_dir.name}/project_example/.deps/captures/duplicate_capture.usda",
            )

            # Check if refresh icon button exists and click it
            refresh_capture_tree_button = ui_test.find(f"{_window.title}//Frame/**/Image[*].name=='Refresh'")
            self.assertIsNotNone(refresh_capture_tree_button)
            await refresh_capture_tree_button.click()
            await ui_test.human_delay(human_delay_speed=5)

            # Ensure there are now two captures
            items = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_title'")
            self.assertEqual(len(items), 2)

            # Delete the duplicate capture
            os.remove(f"{temp_dir.name}/project_example/.deps/captures/duplicate_capture.usda")
            await ui_test.human_delay(human_delay_speed=3)

            # Refresh again
            await refresh_capture_tree_button.click()
            await ui_test.human_delay(human_delay_speed=5)

            # Ensure there is only one capture
            items = ui_test.find_all(f"{_window.title}//Frame/**/Label[*].identifier=='item_title'")
            self.assertEqual(len(items), 1)

            await self.__destroy(_window, _wid)

    async def test_delete_capture_path(self):
        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            # Setup
            shutil.copytree(_get_test_data("usd/project_example"), f"{temp_dir.name}/project_example")
            await open_stage(f"{temp_dir.name}/project_example/combined.usda")
            _window, _wid = await self.__setup_widget("test_capture_item_centered")  # Keep in memory during test
            await ui_test.human_delay(human_delay_speed=10)

            # Select capture path text field, save orig path, and ensure empty path label not visible
            capture_path_field = ui_test.find(f"{_window.title}//Frame/**/StringField[*].name=='CapturePathField'")
            empty_path_label = ui_test.find(
                f"{_window.title}//Frame/**/Label[*].name=='USDPropertiesWidgetValueOverlay'"
            )
            self.assertIsNotNone(capture_path_field)
            original_capture_path = capture_path_field.widget.model.get_value_as_string()
            self.assertFalse(empty_path_label.widget.visible)

            # Select and delete the contents of the string field
            await capture_path_field.double_click()
            await ui_test.emulate_keyboard_press(carb_input.KeyboardInput.DEL)

            # Ensure that the model path is empty
            self.assertEqual(capture_path_field.widget.model.get_value_as_string(), "")

            # Ensure that the empty field label is visible and accurate
            self.assertTrue(empty_path_label.widget.visible)
            self.assertEqual(empty_path_label.widget.text, "Capture directory path...")

            # Press enter and ensure  the origi path has returned and label is not visible/overlapping
            await ui_test.emulate_keyboard_press(carb_input.KeyboardInput.ENTER)
            self.assertEqual(capture_path_field.widget.model.get_value_as_string(), original_capture_path)
            self.assertFalse(empty_path_label.widget.visible)

            await self.__destroy(_window, _wid)
