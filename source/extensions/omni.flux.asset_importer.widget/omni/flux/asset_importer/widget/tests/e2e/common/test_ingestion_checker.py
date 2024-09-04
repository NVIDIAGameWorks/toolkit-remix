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

import random
from pathlib import Path
from tempfile import TemporaryDirectory

import omni.kit
import omni.kit.test
import omni.ui as ui
import omni.usd
from omni.flux.asset_importer.core.data_models import SUPPORTED_ASSET_EXTENSIONS, SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.asset_importer.widget.common.ingestion_checker import (
    DIALOG_TITLE,
    file_validation_failed_callback,
    texture_validation_failed_callback,
)
from omni.kit import ui_test


class TestIngestionCheckerE2E(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.stage = omni.usd.get_context().get_stage()
        self.temp_dir = TemporaryDirectory()  # pylint: disable=consider-using-with

    # After running each test
    async def tearDown(self):
        self.temp_dir.cleanup()
        self._destroy_excess_windows()
        self.stage = None
        self.temp_dir = None

    def _destroy_excess_windows(self):
        for other_window in ui.Workspace.get_windows():
            prompt_dialog_window = ui_test.find(other_window.title)
            if other_window.title == DIALOG_TITLE:
                prompt_dialog_window.widget.destroy()

    async def test_validation_failed_callback_extensions(self):
        bad_count = random.randrange(1, 20)
        filenames = [f"{num}.BAD" for num in range(bad_count)]

        # Simulate a failure callback
        file_validation_failed_callback(filenames)

        await ui_test.human_delay(100)
        error_window = ui_test.find(DIALOG_TITLE)
        self.assertIsNotNone(error_window)

        msg_label0 = ui_test.find(f"{DIALOG_TITLE}//Frame/**/Label[*].identifier=='msg_label0'")
        msg_label1 = ui_test.find(f"{DIALOG_TITLE}//Frame/**/Label[*].identifier=='msg_label1'")
        self.assertTrue("following file types" in msg_label0.widget.text)
        msg1_text = msg_label1.widget.text
        for supported_ext in SUPPORTED_ASSET_EXTENSIONS:
            self.assertTrue(supported_ext in msg1_text)

        bad_label = ui_test.find_all(f"{DIALOG_TITLE}//Frame/**/Label[*].identifier=='bad_label'")
        bad_label = bad_label[-1]
        self.assertTrue("Invalid file path" in bad_label.widget.text)

        content_field = ui_test.find(f"{DIALOG_TITLE}//Frame/**/StringField[*].identifier=='content_string_field'")
        self.assertIsNotNone(content_field)
        content = content_field.model.get_value_as_string()
        for fname in filenames:
            assert fname in content

        # There may be multiple windows due to async running. Close them all.
        error_ok_buttons = ui_test.find_all(
            f"{DIALOG_TITLE}//Frame/**/Button[*].identifier=='ingestion_error_ok_button'"
        )
        for button in error_ok_buttons:
            self.assertIsNotNone(button)
            await ui_test.human_delay()
            await button.click()

    async def test_validation_failed_callback_texture(self):
        bad_count = random.randrange(1, 20)
        filenames = [f"{num}.BAD" for num in range(bad_count)]

        # Simulate a failure callback
        texture_validation_failed_callback(filenames)

        await ui_test.human_delay(100)
        error_window = ui_test.find(DIALOG_TITLE)
        self.assertIsNotNone(error_window)

        msg_label0 = ui_test.find(f"{DIALOG_TITLE}//Frame/**/Label[*].identifier=='msg_label0'")
        msg_label1 = ui_test.find(f"{DIALOG_TITLE}//Frame/**/Label[*].identifier=='msg_label1'")
        self.assertTrue("following file types" in msg_label0.widget.text)
        msg1_text = msg_label1.widget.text
        for supported_ext in SUPPORTED_TEXTURE_EXTENSIONS:
            self.assertTrue(supported_ext in msg1_text)

        bad_label = ui_test.find_all(f"{DIALOG_TITLE}//Frame/**/Label[*].identifier=='bad_label'")
        bad_label = bad_label[-1]
        self.assertTrue("Invalid file path" in bad_label.widget.text)

        content_field = ui_test.find(f"{DIALOG_TITLE}//Frame/**/StringField[*].identifier=='content_string_field'")
        self.assertIsNotNone(content_field)
        content = content_field.model.get_value_as_string()
        for fname in filenames:
            assert fname in content

        # There may be multiple windows due to async running. Close them all.
        error_ok_buttons = ui_test.find_all(
            f"{DIALOG_TITLE}//Frame/**/Button[*].identifier=='ingestion_error_ok_button'"
        )
        for button in error_ok_buttons:
            self.assertIsNotNone(button)
            await ui_test.human_delay()
            await button.click()

    async def test_validation_failed_callback_directories(self):
        bad_count = random.randrange(1, 20)
        # Create the directories
        dirnames = []
        base_folder = Path(self.temp_dir.name)
        for num in range(bad_count):
            nm = f"folder{num}"
            pth = base_folder / nm
            pth.mkdir(parents=True)
            dirnames.append(str(pth))

        # Simulate a failure callback
        texture_validation_failed_callback(dirnames)

        await ui_test.human_delay(100)
        error_window = ui_test.find(DIALOG_TITLE)
        self.assertIsNotNone(error_window)

        msg_label0 = ui_test.find(f"{DIALOG_TITLE}//Frame/**/Label[*].identifier=='msg_label0'")
        msg_label1 = ui_test.find(f"{DIALOG_TITLE}//Frame/**/Label[*].identifier=='msg_label1'")
        self.assertTrue("Directories cannot be ingested" in msg_label0.widget.text)
        self.assertIsNone(msg_label1)

        bad_label = ui_test.find_all(f"{DIALOG_TITLE}//Frame/**/Label[*].identifier=='bad_label'")
        bad_label = bad_label[-1]
        self.assertTrue("Invalid file path" in bad_label.widget.text)

        content_field = ui_test.find(f"{DIALOG_TITLE}//Frame/**/StringField[*].identifier=='content_string_field'")
        self.assertIsNotNone(content_field)
        content = content_field.model.get_value_as_string()
        for dirname in dirnames:
            # dirnames can have Windows backslashes
            clean_name = dirname.replace("\\", "/")
            assert clean_name in content

        # There may be multiple windows due to async running. Close them all.
        error_ok_buttons = ui_test.find_all(
            f"{DIALOG_TITLE}//Frame/**/Button[*].identifier=='ingestion_error_ok_button'"
        )
        for button in error_ok_buttons:
            self.assertIsNotNone(button)
            await ui_test.human_delay()
            await button.click()
            await ui_test.human_delay()
