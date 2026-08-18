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

from unittest import mock

import omni.kit.test

from ...string_value import file_picker as _file_picker
from ...string_value.file_picker import FilePicker


class TestFilePicker(omni.kit.test.AsyncTestCase):
    """Validate explicit relative-path stage resolution."""

    async def test_existing_positional_arguments_keep_their_bindings(self):
        """Adding the keyword-only stage resolver preserves the existing positional API."""
        # Arrange / Act
        picker = FilePicker(None, "LegacyStyle", False, "field_identifier", "picker_identifier")

        # Assert
        self.assertEqual(picker.style_name, "LegacyStyle")
        self.assertEqual(picker.identifier, "field_identifier")
        self.assertEqual(picker._picker_identifier, "picker_identifier")

    async def test_relative_paths_without_stage_resolver_raises_value_error(self):
        """Relative-path mode requires an explicitly declared stage resolver."""
        # Arrange / Act / Assert
        with self.assertRaisesRegex(ValueError, "stage resolver"):
            FilePicker(use_relative_paths=True)

    async def test_absolute_paths_without_stage_resolver_sets_selected_path(self):
        """The generic and native path delegate does not require a USD stage."""
        # Arrange
        picker = FilePicker()
        widget = mock.Mock()
        selected_path = "C:/textures/albedo.dds"

        # Act
        picker._set_field(widget, mock.Mock(spec=[]), 0, selected_path)

        # Assert
        widget.model.set_value.assert_called_once_with(selected_path)

    async def test_absolute_paths_with_stage_resolver_does_not_resolve_stage(self):
        """A stage resolver does not opt a delegate into relative-path mode."""
        # Arrange
        stage_resolver = mock.Mock()
        picker = FilePicker(stage_resolver=stage_resolver)
        widget = mock.Mock()
        selected_path = "C:/textures/albedo.dds"

        # Act
        picker._set_field(widget, mock.Mock(), 0, selected_path)

        # Assert
        stage_resolver.assert_not_called()
        widget.model.set_value.assert_called_once_with(selected_path)

    async def test_relative_paths_with_stage_resolver_sets_normalized_path(self):
        """Relative-path mode passes the declared stage to the USD path helper."""
        # Arrange
        stage = object()
        value_model = mock.Mock()
        picker = FilePicker(use_relative_paths=True, stage_resolver=lambda _model: stage)
        widget = mock.Mock()
        with (
            mock.patch.object(
                _file_picker.omni.usd,
                "make_path_relative_to_current_edit_target",
                return_value="..\\textures\\albedo.dds",
            ) as make_relative,
            mock.patch.object(
                _file_picker.omni.client,
                "normalize_url",
                side_effect=lambda path: path,
            ),
        ):
            # Act
            picker._set_field(widget, value_model, 0, "C:/textures/albedo.dds")

        # Assert
        make_relative.assert_called_once_with("C:/textures/albedo.dds", stage=stage)
        widget.model.set_value.assert_called_once_with("../textures/albedo.dds")

    async def test_relative_paths_with_unavailable_stage_preserves_current_value(self):
        """Relative mode never falls back to storing a nonportable absolute path."""
        # Arrange
        picker = FilePicker(use_relative_paths=True, stage_resolver=lambda _model: None)
        widget = mock.Mock()

        # Act
        with mock.patch.object(_file_picker.carb, "log_error") as log_error:
            picker._set_field(widget, mock.Mock(), 0, "C:/textures/albedo.dds")

        # Assert
        widget.model.set_value.assert_not_called()
        log_error.assert_called_once()
