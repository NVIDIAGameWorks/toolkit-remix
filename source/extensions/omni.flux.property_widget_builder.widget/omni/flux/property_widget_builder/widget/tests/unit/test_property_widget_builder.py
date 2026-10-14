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

__all__ = ("TestPropertyWidgetCleanup",)

from unittest.mock import MagicMock, patch

import omni.kit.test
from omni.flux.property_widget_builder.widget import Delegate, Model, PropertyWidget, property_widget_builder


class TestPropertyWidgetCleanup(omni.kit.test.AsyncTestCase):
    """Verify widget cleanup failures without constructing live UI."""

    async def test_destroy_with_failing_delegate_reset_releases_widget_and_reports_error(self):
        """Release widget references and owner callbacks while propagating a delegate cleanup failure."""
        # Arrange
        model = MagicMock(spec=Model)
        model.get_all_items.return_value = []
        delegate = MagicMock(spec=Delegate)
        delegate.field_builders = []
        cleanup_error = RuntimeError("field cleanup failed")
        delegate.reset.side_effect = cleanup_error
        with (
            patch.object(property_widget_builder.ui, "Frame"),
            patch.object(property_widget_builder, "_TreeWidget"),
        ):
            widget = PropertyWidget(model=model, delegate=delegate)

            # Act
            with self.assertRaisesRegex(RuntimeError, "field cleanup failed") as raised:
                widget.destroy()

        # Assert
        self.assertIs(raised.exception, cleanup_error)
        delegate.reset.assert_called_once_with()
        delegate.set_apply_item_expanded_fn.assert_called_with(None)
        self.assertIsNone(widget.tree_view)
        self.assertIsNone(widget._root_frame)
        self.assertIsNone(widget._model)
        self.assertIsNone(widget._delegate)
        self.assertIsNone(widget._on_item_expanded_sub)
        self.assertIsNone(widget._on_item_changed_sub)
