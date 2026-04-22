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
from unittest.mock import patch

import omni.kit.test
import omni.ui as ui
from omni.flux.property_widget_builder.delegates.base import AbstractDragFieldGroup
from omni.flux.utils.widget import FloatBoundedDrag

from .mocks import MockValueModel


class _StubDragField(AbstractDragFieldGroup):
    """Thin concrete subclass for testing AbstractDragFieldGroup logic."""

    def __init__(self, **kwargs):
        kwargs.setdefault("style_name", "StubDragField")
        super().__init__(**kwargs)

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
    ) -> Any:
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


class _StubItem:
    """Minimal item wrapper used for build_ui tests."""

    def __init__(self, value_models):
        self.value_models = value_models
        self.element_count = len(value_models)


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
    # ------------------------------------------------------------------
    # Constructor & property tests
    # ------------------------------------------------------------------

    async def test_stores_min_max_step(self):
        """Constructor should persist min_value, max_value, and _step."""
        # Arrange
        field = _StubDragField(min_value=-5.0, max_value=5.0, step=0.25)

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
        field = _StubDragField(min_value=0.0, max_value=100.0)

        # Act
        step_value = field.step

        # Assert
        self.assertIsNone(step_value)

    async def test_custom_style_name(self):
        """style_name should be forwarded through kwargs."""
        # Arrange
        field = _StubDragField(min_value=0.0, max_value=1.0, style_name="Custom")

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
        field = _StubDragField(min_value=0.0, max_value=1.0, identifier="my_id")

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
        field = _StubDragField()

        # Act
        min_value = field.min_value
        max_value = field.max_value

        # Assert
        self.assertIsNone(min_value)
        self.assertIsNone(max_value)

    async def test_single_bound_min_only(self):
        """Only min_value can be set, leaving max_value as None."""
        # Arrange
        field = _StubDragField(min_value=0.0)

        # Act
        min_value = field.min_value
        max_value = field.max_value

        # Assert
        self.assertEqual(min_value, 0.0)
        self.assertIsNone(max_value)

    async def test_single_bound_max_only(self):
        """Only max_value can be set, leaving min_value as None."""
        # Arrange
        field = _StubDragField(max_value=100.0)

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
        field = _StubDragField(min_value=0.0, max_value=100.0, hard_min_value=-10.0, hard_max_value=110.0)

        # Act
        hard_min_value = field.hard_min_value
        hard_max_value = field.hard_max_value

        # Assert
        self.assertEqual(hard_min_value, -10.0)
        self.assertEqual(hard_max_value, 110.0)

    async def test_hard_bounds_default_none(self):
        """Hard bounds should default to None when omitted."""
        # Arrange
        field = _StubDragField(min_value=0.0, max_value=100.0)

        # Act
        hard_min_value = field.hard_min_value
        hard_max_value = field.hard_max_value

        # Assert
        self.assertIsNone(hard_min_value)
        self.assertIsNone(hard_max_value)

    async def test_end_edit_closes_active_batch_edit(self):
        """end_edit should close an active batch edit when widget mouse release is missed."""
        # Arrange
        field = _StubDragField()
        model = _BatchEditValueModel(value=5.0)
        model.begin_batch_edit()

        # Act
        field.end_edit(model)

        # Assert
        self.assertEqual(model.end_batch_edit_calls, 1)
        self.assertFalse(model.is_batch_editing)

    async def test_build_ui_falls_back_hard_bounds_to_soft_bounds_for_typed_values(self):
        """Missing hard bounds should fall back to soft bounds for typed clamping."""
        # Arrange
        field = _StubDragField(min_value=0.0, max_value=10.0)
        model = MockValueModel(value=0.0)
        item = _StubItem([model])

        # Act
        widgets = field.build_ui(item)
        model.set_value(999.0)

        # Assert
        self.assertEqual(len(widgets), 1)
        self.assertEqual(getattr(widgets[0], "hard_min_value", None), 0.0)
        self.assertEqual(getattr(widgets[0], "hard_max_value", None), 10.0)
        self.assertEqual(model.get_value_as_float(), 10.0)

    async def test_build_ui_prefers_explicit_hard_bounds_over_soft_fallback(self):
        """Explicit hard bounds should override soft min/max fallback for typed clamping."""
        # Arrange
        field = _StubDragField(min_value=0.0, max_value=10.0, hard_min_value=-5.0, hard_max_value=5.0)
        model = MockValueModel(value=0.0)
        item = _StubItem([model])

        # Act
        widgets = field.build_ui(item)
        model.set_value(9.0)

        # Assert
        self.assertEqual(len(widgets), 1)
        self.assertEqual(getattr(widgets[0], "hard_min_value", None), -5.0)
        self.assertEqual(getattr(widgets[0], "hard_max_value", None), 5.0)
        self.assertEqual(model.get_value_as_float(), 5.0)

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
