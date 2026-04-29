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

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import omni.kit.test
from omni.flux.property_widget_builder.model.usd.item_delegates import (
    file_texture_picker as _file_texture_picker_module,
)
from omni.flux.property_widget_builder.model.usd.item_delegates.file_texture_picker import FileTexturePicker
from omni.flux.property_widget_builder.model.usd.item_model.attr_value import UsdAttributeValueModel
from PIL import Image

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

    async def test_on_validation_failed_posts_supported_texture_prompt(self):
        # Arrange
        picker = FileTexturePicker()

        # Act
        with patch.object(_file_texture_picker_module._PromptManager, "post_simple_prompt") as post_prompt_mock:
            picker._on_validation_failed("/textures", "bad.txt")

        # Assert
        post_prompt_mock.assert_called_once()
        args, kwargs = post_prompt_mock.call_args
        self.assertEqual("Invalid Texture File", args[0])
        self.assertIn("Supported texture formats", args[1])
        self.assertTrue(kwargs["modal"])

    async def test_on_navigate_to_uses_normalized_resolved_asset_path(self):
        # Arrange
        picker = FileTexturePicker()
        value_model = MagicMock()
        value_model.get_attributes_raw_value.return_value = SimpleNamespace(
            path="textures/albedo.dds",
            resolvedPath="C:\\Project\\textures\\albedo.dds",
        )

        with (
            patch.object(_file_texture_picker_module._path_utils, "is_file_path_valid", return_value=True),
            patch.object(
                _file_texture_picker_module.omni.client,
                "normalize_url",
                return_value="C:\\Project\\textures\\albedo.dds",
            ),
        ):
            # Act
            fallback, path = picker._on_navigate_to("", value_model, 0)

        # Assert
        self.assertFalse(fallback)
        self.assertEqual("C:/Project/textures/albedo.dds", path)

    async def test_on_navigate_to_falls_back_when_resolved_asset_path_is_empty(self):
        # Arrange
        picker = FileTexturePicker()
        value_model = MagicMock()
        value_model.get_attributes_raw_value.return_value = SimpleNamespace(
            path="textures/albedo.dds",
            resolvedPath="",
        )

        # Act
        fallback, path = picker._on_navigate_to("", value_model, 0)

        # Assert
        self.assertTrue(fallback)
        self.assertIsNone(path)

    async def test_on_navigate_to_uses_root_layer_folder_when_asset_path_is_empty(self):
        # Arrange
        picker = FileTexturePicker()
        value_model = MagicMock()
        value_model.get_attributes_raw_value.return_value = None
        value_model.stage.GetRootLayer.return_value = SimpleNamespace(
            anonymous=False,
            identifier="C:/Project/scene.usda",
        )

        with (
            patch.object(_file_texture_picker_module._path_utils, "is_file_path_valid", return_value=True),
            patch.object(_file_texture_picker_module.omni.client, "normalize_url", side_effect=lambda value: value),
        ):
            # Act
            fallback, path = picker._on_navigate_to("", value_model, 0)

        # Assert
        self.assertTrue(fallback)
        self.assertEqual("C:/Project", path)

    async def test_on_navigate_to_falls_back_when_stage_root_layer_is_anonymous(self):
        # Arrange
        picker = FileTexturePicker()
        value_model = MagicMock()
        value_model.get_attributes_raw_value.return_value = None
        value_model.stage.GetRootLayer.return_value = SimpleNamespace(anonymous=True, identifier="")

        # Act
        fallback, path = picker._on_navigate_to("", value_model, 0)

        # Assert
        self.assertTrue(fallback)
        self.assertIsNone(path)

    async def test_value_model_fallback_path_returns_empty_for_non_usd_value_model(self):
        # Arrange
        picker = FileTexturePicker()
        value_model = MagicMock()
        value_model.get_value_as_string.return_value = "textures/albedo.dds"

        # Act
        fallback_path = picker._FileTexturePicker__get_value_model_fallback_path(value_model)

        # Assert
        self.assertEqual("", fallback_path)

    async def test_value_model_fallback_path_resolves_against_first_non_anonymous_prim_stack_layer(self):
        # Arrange
        picker = FileTexturePicker()
        value_model = UsdAttributeValueModel.__new__(UsdAttributeValueModel)
        value_model.get_value_as_string = MagicMock(return_value="textures/albedo.dds")
        value_model._attributes = [MagicMock()]

        layer = SimpleNamespace(
            anonymous=False,
            ComputeAbsolutePath=lambda path: f"C:/Project/{path}",
        )
        value_model._attributes[0].GetPrim.return_value.GetPrimStack.return_value = [SimpleNamespace(layer=layer)]

        # Act
        fallback_path = picker._FileTexturePicker__get_value_model_fallback_path(value_model)

        # Assert
        self.assertEqual("C:/Project/textures/albedo.dds", fallback_path)

    async def test_open_explorer_uses_parent_folder_for_files(self):
        # Arrange
        picker = FileTexturePicker()

        with tempfile.TemporaryDirectory() as temp_dir:
            texture_path = Path(temp_dir) / "texture.png"
            texture_path.write_text("", encoding="utf-8")

            with patch.object(_file_texture_picker_module.os, "startfile") as startfile_mock:
                # Act
                picker._open_explorer(0, str(texture_path))

        # Assert
        startfile_mock.assert_called_once_with(texture_path.parent)

    async def test_open_explorer_ignores_non_left_mouse_button(self):
        # Arrange
        picker = FileTexturePicker()

        # Act
        with patch.object(_file_texture_picker_module.os, "startfile") as startfile_mock:
            picker._open_explorer(1, "C:/Project/texture.png")

        # Assert
        startfile_mock.assert_not_called()

    async def test_get_resolution_reads_image_dimensions(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temp_dir:
            texture_path = Path(temp_dir) / "texture.png"
            Image.new("RGBA", (8, 4)).save(texture_path)

            # Act
            resolution = FileTexturePicker._get_resolution(str(texture_path))

        # Assert
        self.assertEqual((8, 4), resolution)

    async def test_field_begin_blocks_value_model_writes(self):
        # Arrange
        picker = FileTexturePicker()
        value_model = MagicMock()

        # Act
        picker._on_field_begin(MagicMock(), value_model, 0, MagicMock())

        # Assert
        value_model.block_set_value.assert_called_once_with(True)

    async def test_field_end_unblocks_and_commits_cached_value(self):
        # Arrange
        picker = FileTexturePicker()
        value_model = MagicMock()
        value_model.cached_blocked_value = "textures/albedo.dds"

        # Act
        picker._on_field_end(MagicMock(), value_model, 0, MagicMock())

        # Assert
        value_model.block_set_value.assert_called_once_with(False)
        value_model.set_value.assert_called_once_with("textures/albedo.dds")

    async def test_field_changed_validates_cached_value(self):
        # Arrange
        picker = FileTexturePicker()
        widget = MagicMock()
        value_model = MagicMock()
        value_model.cached_blocked_value = "textures/albedo.dds"

        # Act
        with patch.object(picker, "_FileTexturePicker__is_field_path_valid") as is_field_path_valid_mock:
            picker._on_field_changed(widget, value_model, 0, MagicMock())

        # Assert
        value_model.block_set_value.assert_called_once_with(True)
        is_field_path_valid_mock.assert_called_once_with("textures/albedo.dds", widget, value_model, 0)

    async def test_set_field_writes_relative_normalized_path_when_selection_is_valid(self):
        # Arrange
        picker = FileTexturePicker()
        widget = MagicMock()
        value_model = MagicMock()

        with (
            patch.object(picker, "_FileTexturePicker__is_field_path_valid", return_value=True),
            patch.object(_file_texture_picker_module._FilePicker, "_set_field") as set_field_mock,
            patch.object(
                _file_texture_picker_module.omni.usd,
                "make_path_relative_to_current_edit_target",
                return_value="textures\\albedo.dds",
            ),
            patch.object(
                _file_texture_picker_module.omni.client,
                "normalize_url",
                return_value="textures\\albedo.dds",
            ),
        ):
            # Act
            picker._set_field(widget, value_model, 0, "C:/Project/textures/albedo.dds")

        # Assert
        value_model.block_set_value.assert_called_once_with(False)
        set_field_mock.assert_called_once_with(widget, value_model, 0, "textures/albedo.dds")

    async def test_set_field_does_not_write_when_selection_is_invalid(self):
        # Arrange
        picker = FileTexturePicker()
        value_model = MagicMock()

        with (
            patch.object(picker, "_FileTexturePicker__is_field_path_valid", return_value=False),
            patch.object(_file_texture_picker_module._FilePicker, "_set_field") as set_field_mock,
        ):
            # Act
            picker._set_field(MagicMock(), value_model, 0, "C:/Project/textures/missing.dds")

        # Assert
        value_model.block_set_value.assert_called_once_with(False)
        set_field_mock.assert_not_called()
