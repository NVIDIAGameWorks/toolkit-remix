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

__all__ = ("TestIntFieldUnit",)

import omni.kit.test
from omni.flux.property_widget_builder.delegates.int_value.field import IntField

from .mocks import MockValueModel


class TestIntFieldUnit(omni.kit.test.AsyncTestCase):
    """Unit tests for IntField logic (no UI rendering)."""

    async def test_default_style_name(self):
        """Default style_name should be 'PropertiesWidgetField'."""
        field = IntField()
        self.assertEqual(field.style_name, "PropertiesWidgetField")

    async def test_get_value_from_model_returns_int(self):
        """_get_value_from_model should return an int."""
        field = IntField()
        model = MockValueModel(value=42.7)
        result = field._get_value_from_model(model)
        self.assertIsInstance(result, int)
        self.assertEqual(result, 42)
