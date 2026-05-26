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
import omni.ui as ui
from omni.flux.property_widget_builder.delegates import AbstractDragFieldGroup
from omni.flux.property_widget_builder.widget import Delegate, FieldBuilder, claim_each


class _Delegate(Delegate):
    @property
    def default_attr(self):
        return super().default_attr

    def _build_item_widgets(self, model, item, column_id: int, level: int, expanded: bool):
        return []


class _DragField(AbstractDragFieldGroup):
    def __init__(self):
        super().__init__()
        self.cleanup_count = 0
        self.destroy_count = 0

    def build_drag_widget(
        self,
        model,
        style_type_name_override: str,
        read_only: bool,
        min_val,
        max_val,
        hard_min_val,
        hard_max_val,
        step,
    ):
        raise NotImplementedError

    def build_ui(self, item, **kwargs) -> list[ui.Widget]:
        kwargs["register_cleanup"](self._cleanup)
        return []

    def destroy(self) -> None:
        self.destroy_count += 1
        super().destroy()

    def _cleanup(self) -> None:
        self.cleanup_count += 1


class TestDelegate(omni.kit.test.AsyncTestCase):
    async def test_reset_runs_field_cleanup_without_destroying_shared_builder(self):
        # Arrange
        delegate = _Delegate()
        field = _DragField()
        builder = FieldBuilder(claim_func=claim_each(lambda _: True), build_func=field)
        delegate._build_field_widgets(builder, object())

        # Act
        delegate.reset()

        # Assert
        self.assertEqual(field.cleanup_count, 1)
        self.assertEqual(field.destroy_count, 0)
        self.assertEqual(delegate._field_cleanup_callbacks, [])

    async def test_reset_runs_cleanup_aware_builder_function_cleanup(self):
        # Arrange
        delegate = _Delegate()
        cleanup_calls = []

        def build_func(_item, *, register_cleanup):
            register_cleanup(lambda: cleanup_calls.append("cleanup"))
            return []

        builder = FieldBuilder(
            claim_func=claim_each(lambda _: True),
            build_func=build_func,
            supports_field_cleanup=True,
        )
        delegate._build_field_widgets(builder, object())

        # Act
        delegate.reset()

        # Assert
        self.assertEqual(cleanup_calls, ["cleanup"])
        self.assertEqual(delegate._field_cleanup_callbacks, [])
