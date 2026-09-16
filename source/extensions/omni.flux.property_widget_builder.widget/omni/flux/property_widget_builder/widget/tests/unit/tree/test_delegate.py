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

from types import SimpleNamespace

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


class _EditModel:
    """Record legacy edit-style callbacks registered by the tree delegate."""

    def __init__(self) -> None:
        self.begin_callbacks = []
        self.end_callbacks = []
        self.is_mixed = False

    def add_begin_edit_fn(self, callback) -> None:
        """Record a begin-edit callback."""
        self.begin_callbacks.append(callback)

    def add_end_edit_fn(self, callback) -> None:
        """Record an end-edit callback."""
        self.end_callbacks.append(callback)

    def subscribe_value_changed_fn(self, _callback):
        """Return an opaque value-change subscription for the delegate."""
        return object()


class _BuildingDelegate(_Delegate):
    """Use the base field-builder path for callback-wiring tests."""

    def _build_item_widgets(self, model, item, column_id: int, level: int, expanded: bool):
        """Build item widgets through the production delegate implementation."""
        return Delegate._build_item_widgets(self, model, item, column_id, level, expanded)


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

    async def test_drag_group_factory_receives_panel_coordinator(self):
        """A drag-group factory should receive the delegate's shared link coordinator."""
        # Arrange
        delegate = _Delegate()
        coordinators = []

        def build_func(_item, *, register_cleanup, linked_edit_coordinator):
            register_cleanup(lambda: None)
            coordinators.append(linked_edit_coordinator)
            return []

        builder = FieldBuilder(
            claim_func=claim_each(lambda _: True),
            build_func=build_func,
            supports_field_cleanup=True,
            builds_drag_field_group=True,
        )
        delegate._build_field_widgets(builder, object())

        # Act
        delegate._build_field_widgets(builder, object())

        # Assert
        self.assertEqual(len(coordinators), 2)
        self.assertIs(coordinators[0], coordinators[1])

    async def test_drag_group_builder_does_not_receive_legacy_tree_edit_styling(self):
        """A drag group should own edit styling without duplicate tree callbacks."""
        # Arrange
        delegate = _BuildingDelegate()
        value_model = _EditModel()
        item = SimpleNamespace(value_models=[value_model])

        def build_func(_item, **_kwargs):
            return ui.StringField(style_type_name_override="TestField")

        builder = FieldBuilder(
            claim_func=claim_each(lambda _: True),
            build_func=build_func,
            supports_field_cleanup=True,
            builds_drag_field_group=True,
        )
        delegate._builder_map[id(item)] = builder

        # Act
        delegate._build_widget(None, item, 1, 0, False)

        # Assert
        self.assertEqual(value_model.begin_callbacks, [])
        self.assertEqual(value_model.end_callbacks, [])
