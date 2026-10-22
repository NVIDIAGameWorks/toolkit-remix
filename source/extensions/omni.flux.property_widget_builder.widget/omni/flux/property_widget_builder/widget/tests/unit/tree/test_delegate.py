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
from unittest import mock

import omni.kit.test
import omni.kit.undo
import omni.ui as ui
from omni.flux.property_widget_builder.delegates import AbstractDragFieldGroup
from omni.flux.property_widget_builder.widget import Delegate, FieldBuilder, claim_each
from omni.flux.property_widget_builder.widget.tree.clipboard import AttributeCopyPasteHelper
from omni.flux.property_widget_builder.widget.tests.ui_components import TestItem


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

    async def test_context_menu_keeps_empty_model_outlets_and_hidden_editable_primaries(self):
        """Keep editable outlets and hidden primaries eligible while excluding restricted rows."""
        # Arrange
        delegate = _Delegate()
        normal = TestItem([("Visible", 1)])
        hidden = TestItem([("Hidden", 2)])
        hidden.hidden = True
        outlet = mock.Mock(read_only=False, value_models=[])
        restricted = mock.Mock(read_only=True, value_models=[])
        structural = TestItem([])
        companion = TestItem([("Companion", 3)])
        rows = [normal, hidden, outlet, restricted, structural, companion]
        model = mock.Mock()
        model.get_all_items.return_value = rows
        delegate.selection = [outlet, restricted, structural, companion]
        delegate._builder_map.update({id(row): object() for row in rows[:-1]})
        with (
            mock.patch.object(ui, "Menu"),
            mock.patch.object(ui, "MenuItem") as menu_item,
            mock.patch.object(ui, "Separator"),
            mock.patch.object(ui, "MenuDelegate"),
            mock.patch.object(AttributeCopyPasteHelper, "can_paste", return_value=True) as available,
        ):
            # Act
            delegate._show_context_menu(model, outlet)

        # Assert
        model.get_all_items.assert_called_once_with(include_hidden=True)
        self.assertEqual(
            available.call_args_list,
            [mock.call(target_rows=[normal, hidden, outlet]), mock.call(target_rows=[outlet])],
        )
        items = {call.kwargs["identifier"]: call.kwargs for call in menu_item.call_args_list}
        self.assertTrue(items["paste_selected"]["enabled"])
        self.assertTrue(items["paste_all"]["enabled"])

    async def test_paste_menu_actions_share_helper_entry_without_own_undo_group(self):
        """Route both paste menu actions through the helper without opening another undo group."""
        for identifier in ("paste_selected", "paste_all"):
            with self.subTest(title=identifier):
                # Arrange
                delegate = _Delegate()
                selected = TestItem([("Selected", 1)])
                hidden = TestItem([("Hidden", 2)])
                hidden.hidden = True
                model = mock.Mock()
                model.get_all_items.return_value = [selected, hidden]
                delegate.selection = [selected]
                delegate._builder_map.update({id(selected): object(), id(hidden): object()})
                with (
                    mock.patch.object(ui, "Menu"),
                    mock.patch.object(ui, "MenuItem") as menu_item,
                    mock.patch.object(ui, "Separator"),
                    mock.patch.object(ui, "MenuDelegate"),
                    mock.patch.object(AttributeCopyPasteHelper, "can_paste", return_value=True),
                    mock.patch.object(AttributeCopyPasteHelper, "paste") as paste,
                    mock.patch.object(omni.kit.undo, "group") as group,
                ):
                    delegate._show_context_menu(model, selected)
                    callback = next(
                        call.kwargs["triggered_fn"]
                        for call in menu_item.call_args_list
                        if call.kwargs["identifier"] == identifier
                    )

                    # Act
                    callback()

                # Assert
                expected = [selected] if identifier == "paste_selected" else [selected, hidden]
                paste.assert_called_once_with(target_rows=expected)
                group.assert_not_called()
