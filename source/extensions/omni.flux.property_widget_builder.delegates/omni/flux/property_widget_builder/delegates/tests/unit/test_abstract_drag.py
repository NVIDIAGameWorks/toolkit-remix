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

__all__ = ("TestAbstractDragFieldUnit",)

from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from omni.flux.property_widget_builder.delegates.base import (
    AbstractDragFieldGroup,
    DragFieldGroupCoordinator,
    _LinkedEditController,
)
from omni.flux.utils.widget import FloatBoundedDrag

from .mocks import MockItem, MockValueModel


class _StubDragField(AbstractDragFieldGroup):
    """Thin concrete subclass for testing AbstractDragFieldGroup logic."""

    @staticmethod
    def _get_linked_edit_model_type():
        """Return the Float model factory used by this test drag group."""
        return ui.SimpleFloatModel

    @staticmethod
    def _get_linked_edit_field_type():
        """Return the Float field type used by this test drag group."""
        return ui.FloatField

    @staticmethod
    def _get_linked_edit_value(model):
        """Return the Float value used by this test drag group."""
        return model.get_value_as_float()

    def __init__(self, **kwargs):
        kwargs.setdefault("style_name", "StubDragField")
        super().__init__(**kwargs)
        self.build_drag_widget_calls: list[dict[str, Any]] = []

    def build_drag_widget(
        self,
        model: ui.AbstractValueModel,
        style_type_name_override: str,
        read_only: bool,
        min_val: float | int | None,
        max_val: float | int | None,
        hard_min_val: float | int | None,
        hard_max_val: float | int | None,
        step: float | int | None,
    ) -> ui.Widget:
        self.build_drag_widget_calls.append(
            {
                "min_value": min_val,
                "max_value": max_val,
                "hard_min_value": hard_min_val,
                "hard_max_value": hard_max_val,
                "step": step,
            }
        )
        kwargs: dict[str, Any] = {
            "model": model,
            "style_type_name_override": style_type_name_override,
            "read_only": read_only,
            "hard_min_value": hard_min_val,
            "hard_max_value": hard_max_val,
        }
        if min_val is not None:
            kwargs["min"] = min_val
        if max_val is not None:
            kwargs["max"] = max_val
        if step is not None:
            kwargs["step"] = step
        return FloatBoundedDrag(**kwargs)


class _BatchEditValueModel(MockValueModel):
    def __init__(self, value: float | int = 0.0):
        super().__init__(value=value)
        self._is_batch_editing = False
        self.end_batch_edit_calls = 0

    @property
    def supports_batch_edit(self) -> bool:
        return True

    @property
    def is_batch_editing(self) -> bool:
        return self._is_batch_editing

    def begin_batch_edit(self) -> None:
        self._is_batch_editing = True

    def end_batch_edit(self) -> None:
        self.end_batch_edit_calls += 1
        self._is_batch_editing = False


class TestAbstractDragFieldUnit(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._fields: list[_StubDragField] = []

    async def tearDown(self):
        for field in self._fields:
            field.destroy()
        self._fields.clear()
        await omni.kit.ui_test.wait_n_updates(2)

    def _make_field(self, *args, **kwargs) -> _StubDragField:
        field = _StubDragField(*args, **kwargs)
        self._fields.append(field)
        return field

    async def test_enabling_linked_edit_focuses_first_field(self):
        """Enabling linked state should focus the first field through the generic group."""
        # Arrange
        field = _StubDragField(linkable=True)
        self._fields.append(field)
        item = MockItem([MockValueModel(), MockValueModel(), MockValueModel()])
        field.build_ui(item)
        controller = field._build_states[-1].linked_edit_controller
        self.assertIsNotNone(controller)
        controller.focus_text_edit = AsyncMock()

        # Act
        item.set_linked_edit_enabled(True)
        await omni.kit.ui_test.wait_n_updates(3)

        # Assert
        controller.focus_text_edit.assert_awaited_once_with()

    async def test_disabling_linked_edit_hides_first_field(self):
        """Disabling linked state should hide the first field through the generic group."""
        # Arrange
        field = _StubDragField(linkable=True)
        self._fields.append(field)
        item = MockItem([MockValueModel(), MockValueModel(), MockValueModel()])
        field.build_ui(item)
        controller = field._build_states[-1].linked_edit_controller
        self.assertIsNotNone(controller)
        controller.hide_text_edit = Mock()
        item.set_linked_edit_enabled(True)
        await omni.kit.ui_test.wait_n_updates(3)

        # Act
        item.set_linked_edit_enabled(False)

        # Assert
        controller.hide_text_edit.assert_called_once_with()

    async def test_unlinked_edit_selects_only_active_field_and_preserves_mixed_style(self):
        """An unlinked edit should select only its field without dropping mixed styling."""
        # Arrange
        models = [_BatchEditValueModel(), _BatchEditValueModel(), _BatchEditValueModel()]
        field = _StubDragField(linkable=True)
        self._fields.append(field)
        begin_edit_callbacks = []
        with patch.object(
            models[1],
            "subscribe_begin_edit_fn",
            side_effect=lambda callback: begin_edit_callbacks.append(callback) or object(),
        ):
            widgets = field.build_ui(MockItem(models))
        widgets[1].style_type_name_override = "StubDragFieldMixed"

        # Act
        begin_edit_callbacks[-1](models[1])

        # Assert
        self.assertEqual(
            [widget.style_type_name_override for widget in widgets],
            ["StubDragField", "StubDragFieldSelectedMixed", "StubDragField"],
        )

    async def test_linked_edit_does_not_select_active_field(self):
        """A linked edit should not add selected styling to its active field."""
        # Arrange
        models = [_BatchEditValueModel(), _BatchEditValueModel(), _BatchEditValueModel()]
        field = _StubDragField(linkable=True)
        self._fields.append(field)
        begin_edit_callbacks = []
        item = MockItem(models)
        item.set_linked_edit_enabled(True)
        with patch.object(
            models[1],
            "subscribe_begin_edit_fn",
            side_effect=lambda callback: begin_edit_callbacks.append(callback) or object(),
        ):
            widgets = field.build_ui(item)

        # Act
        begin_edit_callbacks[-1](models[1])

        # Assert
        self.assertEqual(
            [widget.style_type_name_override for widget in widgets],
            ["StubDragField", "StubDragField", "StubDragField"],
        )

    async def test_end_edit_clears_selected_style_and_preserves_mixed_style(self):
        """Ending an edit should clear only the selected style suffix."""
        # Arrange
        models = [_BatchEditValueModel(), _BatchEditValueModel(), _BatchEditValueModel()]
        field = _StubDragField(linkable=True)
        self._fields.append(field)
        end_edit_callbacks = []
        with patch.object(
            models[1],
            "subscribe_end_edit_fn",
            side_effect=lambda callback: end_edit_callbacks.append(callback) or object(),
        ):
            widgets = field.build_ui(MockItem(models))
        widgets[1].style_type_name_override = "StubDragFieldSelectedMixed"

        # Act
        end_edit_callbacks[-1](models[1])

        # Assert
        self.assertEqual(widgets[1].style_type_name_override, "StubDragFieldMixed")

    async def test_linked_groups_share_active_row_coordination(self):
        """Activating a second group should unlink and hide the first group."""
        # Arrange
        coordinator = DragFieldGroupCoordinator()
        first_field = _StubDragField(linkable=True)
        second_field = _StubDragField(linkable=True)
        self._fields.extend((first_field, second_field))
        first_item = MockItem([MockValueModel(), MockValueModel(), MockValueModel()], name="First")
        second_item = MockItem([MockValueModel(), MockValueModel(), MockValueModel()], name="Second")
        first_field.build_ui(first_item, linked_edit_coordinator=coordinator)
        second_field.build_ui(second_item, linked_edit_coordinator=coordinator)
        first_item.set_linked_edit_enabled(True)
        await omni.kit.ui_test.wait_n_updates(3)
        first_controller = first_field._build_states[-1].linked_edit_controller
        second_controller = second_field._build_states[-1].linked_edit_controller
        self.assertIsNotNone(first_controller)
        self.assertIsNotNone(second_controller)
        first_controller.hide_text_edit = Mock()
        second_controller.focus_text_edit = AsyncMock()

        # Act
        second_item.set_linked_edit_enabled(True)
        await omni.kit.ui_test.wait_n_updates(3)

        # Assert
        self.assertFalse(first_item.linked_edit_enabled)
        first_controller.hide_text_edit.assert_called_once_with()
        second_controller.focus_text_edit.assert_awaited_once_with()

    async def test_linked_groups_with_same_label_share_active_row_coordination(self):
        """Activating a same-label group should unlink the previously active item."""
        # Arrange
        coordinator = DragFieldGroupCoordinator()
        first_field = _StubDragField(linkable=True)
        second_field = _StubDragField(linkable=True)
        self._fields.extend((first_field, second_field))
        first_item = MockItem([MockValueModel(), MockValueModel(), MockValueModel()])
        second_item = MockItem([MockValueModel(), MockValueModel(), MockValueModel()])
        first_field.build_ui(first_item, linked_edit_coordinator=coordinator)
        second_field.build_ui(second_item, linked_edit_coordinator=coordinator)
        first_item.set_linked_edit_enabled(True)
        await omni.kit.ui_test.wait_n_updates(3)

        # Act
        second_item.set_linked_edit_enabled(True)
        await omni.kit.ui_test.wait_n_updates(3)

        # Assert
        self.assertFalse(first_item.linked_edit_enabled)
        self.assertTrue(second_item.linked_edit_enabled)

    async def test_editing_another_group_preserves_linked_row(self):
        """Editing another group should not change the explicitly linked row."""
        # Arrange
        coordinator = DragFieldGroupCoordinator()
        first_field = _StubDragField(linkable=True)
        second_field = _StubDragField(linkable=True)
        self._fields.extend((first_field, second_field))
        first_item = MockItem([MockValueModel(), MockValueModel(), MockValueModel()], name="First")
        first_field.build_ui(
            first_item,
            linked_edit_coordinator=coordinator,
        )
        second_models = [MockValueModel(), MockValueModel(), MockValueModel()]
        begin_edit_callbacks = []
        with patch.object(
            second_models[1],
            "subscribe_begin_edit_fn",
            side_effect=lambda callback: begin_edit_callbacks.append(callback) or object(),
        ):
            second_field.build_ui(MockItem(second_models, name="Second"), linked_edit_coordinator=coordinator)
        first_item.set_linked_edit_enabled(True)
        await omni.kit.ui_test.wait_n_updates(3)
        first_controller = first_field._build_states[-1].linked_edit_controller
        self.assertIsNotNone(first_controller)
        first_controller.hide_text_edit = Mock()

        # Act
        begin_edit_callbacks[0](second_models[1])

        # Assert
        self.assertTrue(first_item.linked_edit_enabled)
        first_controller.hide_text_edit.assert_not_called()

    async def test_rebuilding_linked_row_keeps_presentation_without_refocusing_or_leaking(self):
        """A rebuild should mount item state without refocusing or retaining old resources."""
        # Arrange
        coordinator = DragFieldGroupCoordinator()
        models = [MockValueModel(), MockValueModel(), MockValueModel()]
        old_field = _StubDragField(linkable=True)
        new_field = _StubDragField(linkable=True)
        self._fields.extend((old_field, new_field))
        item = MockItem(models)
        old_field.build_ui(
            item,
            linked_edit_coordinator=coordinator,
            register_cleanup=lambda _cleanup: None,
        )
        item.set_linked_edit_enabled(True)
        await omni.kit.ui_test.wait_n_updates(3)
        old_controller = old_field._build_states[-1].linked_edit_controller
        self.assertIsNotNone(old_controller)

        # Act
        new_field.build_ui(
            item,
            linked_edit_coordinator=coordinator,
            register_cleanup=lambda _cleanup: None,
        )
        await omni.kit.ui_test.wait_n_updates(3)

        # Assert
        new_controller = new_field._build_states[-1].linked_edit_controller
        self.assertIsNone(old_controller._unsubscribe_property_edit_cancel)
        self.assertEqual(len(item._linked_edit_changed), 1)
        self.assertFalse(new_controller._text_editor.visible)
        self.assertTrue(all(widget.name == "Link" for widget in new_field._build_states[-1].link_widgets))

    async def test_rebuilt_linked_row_routes_one_later_value_change_through_item_state(self):
        """A mounted rebuild should keep item-owned linked value routing active."""
        # Arrange
        coordinator = DragFieldGroupCoordinator()
        models = [MockValueModel(), MockValueModel(), MockValueModel()]
        old_field = _StubDragField(linkable=True)
        new_field = _StubDragField(linkable=True)
        self._fields.extend((old_field, new_field))
        item = MockItem(models)
        old_field.build_ui(item, linked_edit_coordinator=coordinator, register_cleanup=lambda _cleanup: None)
        item.set_linked_edit_enabled(True)
        await omni.kit.ui_test.wait_n_updates(3)
        new_field.build_ui(item, linked_edit_coordinator=coordinator, register_cleanup=lambda _cleanup: None)

        # Act
        models[2].set_value(6.0)

        # Assert
        self.assertEqual([model.get_value_as_float() for model in models], [6.0, 6.0, 6.0])

    async def test_destroy_cleans_up_linked_edit_controller(self):
        """Destroying a drag group should release its linked text controller."""
        # Arrange
        field = _StubDragField(linkable=True)
        self._fields.append(field)
        item = MockItem([MockValueModel(), MockValueModel(), MockValueModel()])
        field.build_ui(item)
        controller = field._build_states[-1].linked_edit_controller
        self.assertIsNotNone(controller)

        # Act
        field.destroy()

        # Assert
        self.assertIsNone(controller._unsubscribe_property_edit_cancel)

    async def test_linked_edit_state_updates_both_separator_controls(self):
        """Linked state should keep both inter-field controls synchronized."""
        # Arrange
        field = _StubDragField(linkable=True)
        self._fields.append(field)
        item = MockItem([MockValueModel(), MockValueModel(), MockValueModel()])
        field.build_ui(item)
        link_widgets = field._build_states[-1].link_widgets

        # Act
        item.set_linked_edit_enabled(True)

        # Assert
        self.assertEqual(len(link_widgets), 2)
        self.assertTrue(all(widget.name == "Link" for widget in link_widgets))
        self.assertTrue(
            all(widget.tooltip == "Multi-channel edit is on. Click to unlink the fields." for widget in link_widgets)
        )

    async def test_primary_link_click_invokes_the_item_toggle_once(self):
        """A primary link click should invoke the item model's toggle operation once."""
        # Arrange
        field = _StubDragField(linkable=True)
        item = MockItem([MockValueModel(), MockValueModel(), MockValueModel()])
        link = field._get_linked_edit(item)
        item.toggle_linked_edit = Mock()

        # Act
        field._on_link_released(link, 0)

        # Assert
        item.toggle_linked_edit.assert_called_once_with()

    async def test_linked_text_change_writes_once(self):
        """Ending linked text entry should write once through the underlying model."""
        # Arrange
        widget = Mock()
        widget.model.get_value_as_float.return_value = 4.0
        controller = _LinkedEditController(
            widget, ui.SimpleFloatModel, ui.FloatField, lambda model: model.get_value_as_float()
        )
        controller._text_editor_active = True
        controller._on_text_editor_begin(Mock())
        editor_model = Mock()
        editor_model.get_value_as_float.return_value = 5.0

        # Act
        controller._on_text_editor_end(editor_model)

        # Assert
        widget.model.set_value.assert_called_once_with(5.0)
        widget.model.end_edit.assert_called_once_with()

    async def test_linked_text_cancel_balances_edit_without_writing(self):
        """Canceling linked text entry should end editing without committing stale text."""
        # Arrange
        cancel_callbacks = []
        widget = Mock()
        widget.model.subscribe_property_edit_cancel_fn.side_effect = lambda callback: (
            cancel_callbacks.append(callback) or Mock()
        )
        controller = _LinkedEditController(
            widget, ui.SimpleFloatModel, ui.FloatField, lambda model: model.get_value_as_float()
        )
        controller._text_editor = Mock(visible=True)
        controller._text_editor_active = True
        controller._on_text_editor_begin(Mock())

        # Act
        cancel_callbacks[0]()

        # Assert
        widget.model.set_value.assert_not_called()
        widget.model.end_edit.assert_called_once_with()
        self.assertFalse(controller._text_editor.visible)

    # ------------------------------------------------------------------
    # Constructor & property tests
    # ------------------------------------------------------------------

    async def test_stores_min_max_step(self):
        """Constructor should persist min_value, max_value, and _step."""
        # Arrange
        field = self._make_field(min_value=-5.0, max_value=5.0, step=0.25)

        # Act
        min_value = field.min_value
        max_value = field.max_value
        step_value = field.step

        # Assert
        self.assertEqual(min_value, -5.0)
        self.assertEqual(max_value, 5.0)
        self.assertEqual(step_value, 0.25)

    async def test_step_property_returns_none_when_unset(self):
        """The base step property should return None when _step is not set."""
        # Arrange
        field = self._make_field(min_value=0.0, max_value=100.0)

        # Act
        step_value = field.step

        # Assert
        self.assertIsNone(step_value)

    async def test_custom_style_name(self):
        """style_name should be forwarded through kwargs."""
        # Arrange
        field = self._make_field(min_value=0.0, max_value=1.0, style_name="Custom")

        # Act
        style_name = field.style_name

        # Assert
        self.assertEqual(style_name, "Custom")

    async def test_invalid_min_max_raises(self):
        """min_value must be strictly less than max_value."""
        # Arrange / Act / Assert
        with self.assertRaises(ValueError):
            _StubDragField(min_value=100.0, max_value=0.0)

    async def test_equal_min_max_raises(self):
        """Equal min and max should be rejected."""
        # Arrange / Act / Assert
        with self.assertRaises(ValueError):
            _StubDragField(min_value=50.0, max_value=50.0)

    async def test_identifier_forwarded(self):
        """The identifier kwarg defined in AbstractField should propagate."""
        # Arrange
        field = self._make_field(min_value=0.0, max_value=1.0, identifier="my_id")

        # Act
        identifier = field.identifier

        # Assert
        self.assertEqual(identifier, "my_id")

    # ------------------------------------------------------------------
    # Unbounded construction tests (None min/max)
    # ------------------------------------------------------------------

    async def test_unbounded_construction(self):
        """Both min_value and max_value should default to None (unbounded)."""
        # Arrange
        field = self._make_field()

        # Act
        min_value = field.min_value
        max_value = field.max_value

        # Assert
        self.assertIsNone(min_value)
        self.assertIsNone(max_value)

    async def test_single_bound_min_only(self):
        """Only min_value can be set, leaving max_value as None."""
        # Arrange
        field = self._make_field(min_value=0.0)

        # Act
        min_value = field.min_value
        max_value = field.max_value

        # Assert
        self.assertEqual(min_value, 0.0)
        self.assertIsNone(max_value)

    async def test_single_bound_max_only(self):
        """Only max_value can be set, leaving min_value as None."""
        # Arrange
        field = self._make_field(max_value=100.0)

        # Act
        min_value = field.min_value
        max_value = field.max_value

        # Assert
        self.assertIsNone(min_value)
        self.assertEqual(max_value, 100.0)

    # ------------------------------------------------------------------
    # Hard-bounds constructor tests
    # ------------------------------------------------------------------

    async def test_hard_bounds_stored(self):
        """Constructor should persist hard_min_value and hard_max_value."""
        # Arrange
        field = self._make_field(min_value=0.0, max_value=100.0, hard_min_value=-10.0, hard_max_value=110.0)

        # Act
        hard_min_value = field.hard_min_value
        hard_max_value = field.hard_max_value

        # Assert
        self.assertEqual(hard_min_value, -10.0)
        self.assertEqual(hard_max_value, 110.0)

    async def test_hard_bounds_default_none(self):
        """Hard bounds should default to None when omitted."""
        # Arrange
        field = self._make_field(min_value=0.0, max_value=100.0)

        # Act
        hard_min_value = field.hard_min_value
        hard_max_value = field.hard_max_value

        # Assert
        self.assertIsNone(hard_min_value)
        self.assertIsNone(hard_max_value)

    async def test_end_edit_closes_active_batch_edit(self):
        """end_edit should close an active batch edit when widget mouse release is missed."""
        # Arrange
        field = self._make_field()
        model = _BatchEditValueModel(value=5.0)
        model.begin_batch_edit()

        # Act
        field.end_edit(model)

        # Assert
        self.assertEqual(model.end_batch_edit_calls, 1)
        self.assertFalse(model.is_batch_editing)

    async def test_build_ui_keeps_soft_bounds_out_of_typed_value_clamping(self):
        """Missing hard bounds should leave typed values unclamped."""
        # Arrange
        field = self._make_field(min_value=0.0, max_value=10.0)
        model = MockValueModel(value=0.0)
        item = MockItem([model])

        # Act
        widgets = field.build_ui(item)
        model.set_value(999.0)

        # Assert
        self.assertEqual(len(widgets), 1)
        widget = cast(FloatBoundedDrag, widgets[0])
        self.assertIsNone(widget.hard_min_value)
        self.assertIsNone(widget.hard_max_value)
        self.assertEqual(model.get_value_as_float(), 999.0)

    async def test_build_ui_uses_explicit_hard_bounds_for_typed_clamping(self):
        """Explicit hard bounds should control typed clamping independently from soft min/max."""
        # Arrange
        field = self._make_field(min_value=0.0, max_value=10.0, hard_min_value=-5.0, hard_max_value=5.0)
        model = MockValueModel(value=0.0)
        item = MockItem([model])

        # Act
        widgets = field.build_ui(item)
        model.set_value(9.0)

        # Assert
        self.assertEqual(len(widgets), 1)
        widget = cast(FloatBoundedDrag, widgets[0])
        self.assertEqual(widget.hard_min_value, -5.0)
        self.assertEqual(widget.hard_max_value, 5.0)
        self.assertEqual(model.get_value_as_float(), 5.0)

    async def test_build_ui_allows_hard_min_with_soft_max(self):
        """Mixed bounds should clamp below hard_min while allowing values above soft max."""
        # Arrange
        field = _StubDragField(hard_min_value=0.0, max_value=10.0)
        model = MockValueModel(value=0.0)
        item = MockItem([model])

        # Act
        widgets = field.build_ui(item)
        model.set_value(-5.0)
        clamped_value = model.get_value_as_float()
        model.set_value(999.0)

        # Assert
        self.assertEqual(len(widgets), 1)
        widget = cast(FloatBoundedDrag, widgets[0])
        self.assertEqual(widget.hard_min_value, 0.0)
        self.assertIsNone(widget.hard_max_value)
        self.assertEqual(clamped_value, 0.0)
        self.assertEqual(model.get_value_as_float(), 999.0)

    async def test_build_ui_uses_hard_min_as_missing_drag_min(self):
        """A hard lower bound should also bound dragging when no soft min is provided."""
        # Arrange
        field = _StubDragField(hard_min_value=0.0, max_value=10.0)
        model = MockValueModel(value=0.0)
        item = MockItem([model])

        # Act
        widgets = field.build_ui(item)

        # Assert
        self.assertEqual(len(widgets), 1)
        self.assertEqual(widgets[0].min, 0.0)
        self.assertEqual(widgets[0].max, 10.0)
        widget = cast(FloatBoundedDrag, widgets[0])
        self.assertEqual(widget.hard_min_value, 0.0)
        self.assertIsNone(widget.hard_max_value)

    async def test_build_ui_uses_hard_max_as_missing_drag_max(self):
        """A hard upper bound should also bound dragging when no soft max is provided."""
        # Arrange
        field = _StubDragField(min_value=0.0, hard_max_value=10.0)
        model = MockValueModel(value=0.0)
        item = MockItem([model])

        # Act
        widgets = field.build_ui(item)

        # Assert
        self.assertEqual(len(widgets), 1)
        self.assertEqual(widgets[0].min, 0.0)
        self.assertEqual(widgets[0].max, 10.0)
        widget = cast(FloatBoundedDrag, widgets[0])
        self.assertIsNone(widget.hard_min_value)
        self.assertEqual(widget.hard_max_value, 10.0)

    async def test_build_ui_forwards_invalid_mixed_bounds_without_promoting_soft_to_hard(self):
        """Invalid mixed drag bounds should not affect hard typed-value clamps."""
        # Arrange
        field = _StubDragField(hard_min_value=20.0, max_value=10.0)
        model = MockValueModel(value=0.0)
        item = MockItem([model])

        # Act
        widgets = field.build_ui(item)
        model.set_value(15.0)
        clamped_value = model.get_value_as_float()

        # Assert
        self.assertEqual(len(widgets), 1)
        self.assertIsNone(field.build_drag_widget_calls[0]["min_value"])
        self.assertEqual(field.build_drag_widget_calls[0]["max_value"], 10.0)
        widget = cast(FloatBoundedDrag, widgets[0])
        self.assertEqual(widget.hard_min_value, 20.0)
        self.assertIsNone(widget.hard_max_value)
        self.assertEqual(clamped_value, 20.0)

    async def test_resolve_scalar_component_returns_value_when_scalar_index_none(self):
        """None scalar index should return the bounds payload unchanged."""
        # Arrange
        value = [1.0, 2.0, 3.0]

        # Act
        result = _StubDragField._resolve_scalar_component(value, None)

        # Assert
        self.assertIs(result, value)

    async def test_resolve_scalar_component_returns_none_on_index_error(self):
        """Out-of-range scalar index should return None."""
        # Arrange
        value = [1.0]
        with patch("omni.flux.property_widget_builder.delegates.base.carb.log_error") as mock_log_error:
            # Act
            result = _StubDragField._resolve_scalar_component(value, 5)

            # Assert
            self.assertIsNone(result)
            mock_log_error.assert_called_once()

    async def test_resolve_scalar_component_logs_error_on_bad_indexable(self):
        """Non-indexable bounds payload should log and return None."""
        # Arrange
        value = cast(Any, object())
        with patch("omni.flux.property_widget_builder.delegates.base.carb.log_error") as mock_log_error:
            # Act
            result = _StubDragField._resolve_scalar_component(value, 0)

            # Assert
            self.assertIsNone(result)
            mock_log_error.assert_called_once()

    async def test_build_ui_passes_configured_step_to_drag(self):
        """Configured delegate step should drive the drag widget."""
        # Arrange
        field = self._make_field(step=0.25)
        item = MockItem([MockValueModel(value=0.0)])

        # Act
        widgets = field.build_ui(item)

        # Assert
        self.assertEqual(len(widgets), 1)
        self.assertEqual(cast(FloatBoundedDrag, widgets[0]).step, 0.25)

    async def test_build_ui_passes_per_component_steps(self):
        """Vector step metadata should be resolved per component."""
        # Arrange
        field = self._make_field(step=[0.25, 0.5, 0.75])
        item = MockItem([MockValueModel(value=0.0), MockValueModel(value=0.0), MockValueModel(value=0.0)])

        # Act
        widgets = field.build_ui(item)

        # Assert
        self.assertEqual([cast(FloatBoundedDrag, widget).step for widget in widgets], [0.25, 0.5, 0.75])
