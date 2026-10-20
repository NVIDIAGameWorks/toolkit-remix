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

__all__ = ("TestItem",)

from unittest import mock

import omni.kit.test
import omni.kit.undo
from omni.flux.property_widget_builder.widget.tests.ui_components import TestItem as _TestItem


class TestItem(omni.kit.test.AsyncTestCase):
    """Exercise ordinary row dispatch while preserving existing model policies."""

    async def test_set_row_values_checks_cardinality_before_any_write(self):
        """Reject mismatched value counts before refreshing or writing any component."""
        for values in ((), (1,), (1, 2, 3)):
            with self.subTest(title=f"values={values}"):
                # Arrange
                row = _TestItem([("X", 5), ("Y", 6)])
                with (
                    mock.patch.object(row.value_models[0], "refresh") as refresh,
                    mock.patch.object(row.value_models[0], "set_value") as write,
                    mock.patch.object(omni.kit.undo, "group") as group,
                ):
                    # Act
                    with self.assertRaises(ValueError):
                        row.set_row_values(values)

                # Assert
                refresh.assert_not_called()
                write.assert_not_called()
                group.assert_not_called()
                self.assertEqual(row.get_value(), [5, 6])

    async def test_set_row_values_refreshes_each_channel_after_previous_write_without_grouping(self):
        """Refresh each component immediately before its write without owning an undo group."""
        # Arrange
        row = _TestItem([("X", 5), ("Y", 6)])
        calls = mock.Mock()
        with (
            mock.patch.object(row.value_models[0], "refresh") as first_refresh,
            mock.patch.object(row.value_models[0], "set_value") as first_write,
            mock.patch.object(row.value_models[1], "refresh") as second_refresh,
            mock.patch.object(row.value_models[1], "set_value") as second_write,
            mock.patch.object(omni.kit.undo, "group") as group,
        ):
            calls.attach_mock(first_refresh, "refresh_x")
            calls.attach_mock(first_write, "write_x")
            calls.attach_mock(second_refresh, "refresh_y")
            calls.attach_mock(second_write, "write_y")

            # Act
            row.set_row_values((1, 2))

        # Assert
        self.assertEqual(
            calls.mock_calls,
            [mock.call.refresh_x(), mock.call.write_x(1), mock.call.refresh_y(), mock.call.write_y(2)],
        )
        group.assert_not_called()

    async def test_set_row_values_preserves_model_callback_and_link_state(self):
        """Use existing model callbacks without changing the row's link state."""
        # Arrange
        row = _TestItem([("Field", 0)])
        row.set_linked_edit_enabled(True)
        callback = mock.Mock(side_effect=lambda setter, value: setter(min(10, value)))
        row.value_models[0].set_callback_pre_set_value(callback)

        # Act
        row.set_row_values((25,))

        # Assert
        self.assertEqual(row.get_value(), [10])
        callback.assert_called_once()
        self.assertEqual(callback.call_args.args[1], 25)
        self.assertTrue(row.linked_edit_enabled)
