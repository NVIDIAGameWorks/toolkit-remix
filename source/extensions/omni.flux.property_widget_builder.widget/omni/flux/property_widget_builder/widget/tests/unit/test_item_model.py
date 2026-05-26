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

import omni.kit.test
from omni.flux.property_widget_builder.widget import ItemValueModel


class _TestValueModel(ItemValueModel):
    def __init__(self):
        super().__init__()
        self._value = 0

    def get_value(self):
        return self._value

    def _set_value(self, value):
        self._value = value

    def _on_dirty(self):
        pass

    def refresh(self):
        pass

    def _get_value_as_string(self) -> str:
        return str(self._value)

    def _get_value_as_float(self) -> float:
        return float(self._value)

    def _get_value_as_bool(self) -> bool:
        return False

    def _get_value_as_int(self) -> int:
        return int(self._value)


class TestItemValueModel(omni.kit.test.AsyncTestCase):
    async def test_cancel_property_edit_interaction_runs_all_callbacks_before_reraising(self):
        # Arrange
        model = _TestValueModel()
        calls = []

        def failing_callback():
            calls.append("failing")
            raise RuntimeError("cancel failed")

        def cleanup_callback():
            calls.append("cleanup")

        model.subscribe_property_edit_cancel_fn(failing_callback)
        model.subscribe_property_edit_cancel_fn(cleanup_callback)

        # Act
        with self.assertRaises(RuntimeError):
            model.cancel_property_edit_interaction()

        # Assert
        self.assertEqual(calls, ["failing", "cleanup"])

    async def test_end_edit_without_begin_edit_skips_property_end_callback(self):
        # Arrange
        model = _TestValueModel()
        calls = []
        model.set_property_edit_callbacks(lambda _: calls.append("begin"), lambda _: calls.append("end"))

        # Act
        model.end_edit()

        # Assert
        self.assertEqual(calls, [])

    async def test_reentrant_property_edit_runs_end_callback_for_each_begin_callback(self):
        # Arrange
        model = _TestValueModel()
        calls = []
        model.set_property_edit_callbacks(lambda _: calls.append("begin"), lambda _: calls.append("end"))

        # Act
        model.begin_edit()
        model.begin_edit()
        model.end_edit()
        model.end_edit()

        # Assert
        self.assertEqual(calls, ["begin", "begin", "end", "end"])
