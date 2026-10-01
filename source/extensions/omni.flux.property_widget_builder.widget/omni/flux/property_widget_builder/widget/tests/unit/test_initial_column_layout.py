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

__all__ = ("TestInitialColumnLayout",)

from unittest.mock import MagicMock, patch

import omni.kit.test
import omni.ui as ui
from omni.flux.property_widget_builder.widget import property_widget_builder
from omni.flux.property_widget_builder.widget import PropertyWidget


class TestInitialColumnLayout(omni.kit.test.AsyncTestCase):
    """Verify initial column sizing without constructing live UI."""

    async def test_first_size_callback_with_unchanged_column_width_does_not_dirty_tree(self):
        """Avoid dirtying property rows when the initial name column width is unchanged."""
        # Arrange
        widget = PropertyWidget.__new__(PropertyWidget)
        widget._model = MagicMock()
        widget._delegate = MagicMock()
        widget._tree_column_widths = [ui.Pixel(150), ui.Fraction(1)]
        widget._tree_min_column_widths = [ui.Pixel(100), ui.Pixel(100)]
        widget._columns_resizable = True
        widget._select_all_children = False
        widget._root_frame = None
        widget._last_name_column_width = None
        frame = MagicMock()
        frame.computed_width = 0
        tree = MagicMock()

        with (
            patch.object(property_widget_builder.ui, "Frame", return_value=frame),
            patch.object(property_widget_builder, "_TreeWidget", return_value=tree),
        ):
            widget._build_ui()
            frame.computed_width = 500

            # Act
            widget._on_content_size_changed()

        # Assert
        tree.dirty_widgets.assert_not_called()
