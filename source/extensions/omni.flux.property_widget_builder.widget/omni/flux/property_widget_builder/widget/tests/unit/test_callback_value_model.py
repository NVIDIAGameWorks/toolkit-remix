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

__all__ = ("TestCallbackValueModel",)

import pathlib

import omni.kit.test
from omni.flux.property_widget_builder.widget import CallbackValueModel


class TestCallbackValueModel(omni.kit.test.AsyncTestCase):
    async def test_edits_reach_the_owner_and_notify_only_on_change(self):
        """Store an edit through the setter and notify the fields, but not when the value is unchanged."""
        stored = {"value": 1.0}
        model = CallbackValueModel(float, lambda: stored["value"], lambda value: stored.update(value=value))
        notifications = []
        model.add_value_changed_fn(lambda _model: notifications.append(model.get_value()))

        model.set_value(2.5)
        model.set_value(2.5)

        self.assertEqual(stored["value"], 2.5)
        self.assertEqual(notifications, [2.5])
        self.assertEqual(model.get_value_as_float(), 2.5)
        self.assertEqual(model.get_value_as_int(), 2)
        self.assertFalse(model.read_only)

    async def test_path_text_becomes_a_path_and_an_empty_path_shows_as_empty_text(self):
        """Convert text from a string field to a path, and show an empty path as an empty string."""
        stored = {"value": pathlib.Path()}
        model = CallbackValueModel(pathlib.Path, lambda: stored["value"], lambda value: stored.update(value=value))

        self.assertEqual(model.get_value_as_string(), "")
        model.set_value("C:/models/chair.usda")

        self.assertEqual(stored["value"], pathlib.Path("C:/models/chair.usda"))
        self.assertEqual(model.get_value_as_string(), str(pathlib.Path("C:/models/chair.usda")))

    async def test_a_value_that_is_not_a_number_shows_as_zero(self):
        """Show zero in a numeric field when the value does not convert."""
        model = CallbackValueModel(str, lambda: "text", lambda _value: None)

        self.assertEqual(model.get_value_as_float(), 0.0)
        self.assertEqual(model.get_value_as_int(), 0)
