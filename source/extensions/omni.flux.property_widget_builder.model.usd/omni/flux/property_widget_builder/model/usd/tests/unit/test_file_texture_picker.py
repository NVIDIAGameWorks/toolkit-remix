"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from unittest.mock import MagicMock, patch

import omni.kit.test
from omni.flux.property_widget_builder.model.usd.item_delegates.file_texture_picker import FileTexturePicker

_OPEN_FILE_PICKER_TARGET = "omni.flux.property_widget_builder.delegates.string_value.file_picker._open_file_picker"


class TestFileTexturePicker(omni.kit.test.AsyncTestCase):
    """Tests for FileTexturePicker, focusing on texture file extension validation (REMIX-3411)."""

    async def test_valid_texture_extensions_are_accepted(self):
        # Arrange
        picker = FileTexturePicker()

        for ext in [".dds", ".png", ".jpg", ".jpeg", ".tga", ".bmp", ".hdr", ".psd"]:
            with self.subTest(ext=ext):
                # Act / Assert
                self.assertTrue(
                    picker._validate_selection("/some/dir/", f"texture{ext}"),
                    f"{ext!r} should be accepted as a texture",
                )

    async def test_invalid_extensions_are_rejected(self):
        # Arrange
        picker = FileTexturePicker()

        for ext in [".txt", ".exe", ".pdf", ".mp4", ".usda", ".py"]:
            with self.subTest(ext=ext):
                # Act / Assert
                self.assertFalse(
                    picker._validate_selection("/some/dir/", f"file{ext}"),
                    f"{ext!r} should be rejected as a texture",
                )

    async def test_empty_filename_passes_validation(self):
        # Arrange
        picker = FileTexturePicker()

        # Act / Assert
        self.assertTrue(picker._validate_selection("/some/dir/", ""), "Empty filename should pass validation")

    async def test_validate_selection_passed_to_file_picker(self):
        # Arrange
        picker = FileTexturePicker()
        mock_widget = MagicMock()
        mock_widget.model.get_value_as_string.return_value = ""
        mock_value_model = MagicMock()

        captured = {}

        def fake_open_file_picker(*args, **kwargs):
            captured["validate_selection"] = kwargs.get("validate_selection")
            captured["validation_failed_callback"] = kwargs.get("validation_failed_callback")

        # Act
        with patch.object(picker, "_on_navigate_to", return_value=(True, None)):
            with patch(_OPEN_FILE_PICKER_TARGET, side_effect=fake_open_file_picker):
                picker._on_open_file_pressed(mock_widget, mock_value_model, 0, 0, 0, 0, 0)

        # Assert
        self.assertEqual(captured["validate_selection"], picker._validate_selection)
        self.assertEqual(captured["validation_failed_callback"], picker._on_validation_failed)

    async def test_button_not_zero_does_not_open_picker(self):
        # Arrange
        picker = FileTexturePicker()
        mock_widget = MagicMock()
        mock_widget.model.get_value_as_string.return_value = ""
        mock_value_model = MagicMock()

        # Act / Assert
        with patch(_OPEN_FILE_PICKER_TARGET) as mock_open:
            picker._on_open_file_pressed(mock_widget, mock_value_model, 0, 0, 0, 1, 0)  # button=1
            mock_open.assert_not_called()
