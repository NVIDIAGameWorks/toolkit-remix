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

__all__ = ("TestFieldBuilder",)

import omni.kit.clipboard
import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from omni.flux.property_widget_builder.widget import FieldBuilderList

from ...ui_components import AsyncTestPropertyWidget, TestItem


class TestFieldBuilder(omni.kit.test.AsyncTestCase):
    async def test_custom_widget_builder(self):

        field_builders = FieldBuilderList()

        @field_builders.register_build(lambda _: True)
        def build_any(item) -> list[ui.Widget]:
            """
            Fallback build method that will claim anything.
            """
            widget = ui.StringField(
                model=item.value_models[0],
                identifier="TestStringField",
            )
            return [widget]

        @field_builders.register_build(lambda x: x.get_value() == ["V_2"])
        def build_label(item) -> list[ui.Widget]:
            """
            Custom builder method if the item value equals "V_2"
            """
            widget = ui.Label(
                item.value_models[0].get_value_as_string(),
                identifier="TestLabel",
            )
            return [widget]

        async with AsyncTestPropertyWidget() as helper:

            helper.delegate.field_builders = field_builders

            items = [
                TestItem([("N_1", "V_1")]),
                TestItem([("N_2", "V_2")]),
                TestItem([("N_3", "V_3")]),
            ]
            await helper.set_items(items)

            string_field_refs = omni.kit.ui_test.find_all(
                f"{helper.window.title}//Frame/**/StringField[*].identifier=='TestStringField'"
            )
            self.assertTrue(len(string_field_refs) == 2, "Expected two TestStringField widgets")

            label_field_refs = omni.kit.ui_test.find_all(
                f"{helper.window.title}//Frame/**/Label[*].identifier=='TestLabel'"
            )
            self.assertTrue(len(label_field_refs) == 1, "Expected a single TestLabel widget")
