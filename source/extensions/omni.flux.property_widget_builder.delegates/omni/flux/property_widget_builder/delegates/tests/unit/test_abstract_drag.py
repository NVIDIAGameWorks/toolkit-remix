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

from typing import Any

import omni.kit.test
import omni.ui as ui
from omni.flux.property_widget_builder.delegates.base import AbstractDragField

from .mocks import MockValueModel


class _StubDragField(AbstractDragField):
    """Thin concrete subclass for testing AbstractDragField logic."""

    def __init__(self, **kwargs):
        kwargs.setdefault("style_name", "StubDragField")
        super().__init__(**kwargs)

    def _get_value_from_model(self, model) -> float:
        return model.get_value_as_float()

    def build_drag_widget(
        self,
        model: ui.AbstractValueModel,
        style_type_name_override: str,
        read_only: bool,
        min_val: float | int | None,
        max_val: float | int | None,
        step: float | int | None,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": model,
            "style_type_name_override": style_type_name_override,
            "read_only": read_only,
        }
        if min_val is not None:
            kwargs["min"] = min_val
        if max_val is not None:
            kwargs["max"] = max_val
        if step is not None:
            kwargs["step"] = step
        return ui.FloatDrag(**kwargs)


class TestAbstractDragFieldUnit(omni.kit.test.AsyncTestCase):
    # ------------------------------------------------------------------
    # Constructor & property tests
    # ------------------------------------------------------------------

    async def test_stores_min_max_step(self):
        """Constructor should persist min_value, max_value, and _step."""
        field = _StubDragField(min_value=-5.0, max_value=5.0, step=0.25)
        self.assertEqual(field.min_value, -5.0)
        self.assertEqual(field.max_value, 5.0)
        self.assertEqual(field.step, 0.25)

    async def test_step_property_returns_none_when_unset(self):
        """The base step property should return None when _step is not set."""
        field = _StubDragField(min_value=0.0, max_value=100.0)
        self.assertIsNone(field.step)

    async def test_custom_style_name(self):
        """style_name should be forwarded through kwargs."""
        field = _StubDragField(min_value=0.0, max_value=1.0, style_name="Custom")
        self.assertEqual(field.style_name, "Custom")

    async def test_invalid_min_max_raises(self):
        """min_value must be strictly less than max_value."""
        with self.assertRaises(ValueError):
            _StubDragField(min_value=100.0, max_value=0.0)

    async def test_equal_min_max_raises(self):
        """Equal min and max should be rejected."""
        with self.assertRaises(ValueError):
            _StubDragField(min_value=50.0, max_value=50.0)

    async def test_identifier_forwarded(self):
        """The identifier kwarg defined in AbstractField should propagate."""
        field = _StubDragField(min_value=0.0, max_value=1.0, identifier="my_id")
        self.assertEqual(field.identifier, "my_id")

    # ------------------------------------------------------------------
    # Unbounded construction tests (None min/max)
    # ------------------------------------------------------------------

    async def test_unbounded_construction(self):
        """Both min_value and max_value should default to None (unbounded)."""
        field = _StubDragField()
        self.assertIsNone(field.min_value)
        self.assertIsNone(field.max_value)

    async def test_single_bound_min_only(self):
        """Only min_value can be set, leaving max_value as None."""
        field = _StubDragField(min_value=0.0)
        self.assertEqual(field.min_value, 0.0)
        self.assertIsNone(field.max_value)

    async def test_single_bound_max_only(self):
        """Only max_value can be set, leaving min_value as None."""
        field = _StubDragField(max_value=100.0)
        self.assertIsNone(field.min_value)
        self.assertEqual(field.max_value, 100.0)

    # ------------------------------------------------------------------
    # Hard-bounds constructor tests
    # ------------------------------------------------------------------

    async def test_hard_bounds_stored(self):
        """Constructor should persist hard_min_value and hard_max_value."""
        field = _StubDragField(min_value=0.0, max_value=100.0, hard_min_value=-10.0, hard_max_value=110.0)
        self.assertEqual(field.hard_min_value, -10.0)
        self.assertEqual(field.hard_max_value, 110.0)

    async def test_hard_bounds_default_none(self):
        """Hard bounds should default to None when omitted."""
        field = _StubDragField(min_value=0.0, max_value=100.0)
        self.assertIsNone(field.hard_min_value)
        self.assertIsNone(field.hard_max_value)

    # ------------------------------------------------------------------
    # _clamp_to_hard_bounds tests (both bounds)
    # ------------------------------------------------------------------

    async def test_clamp_below_hard_min(self):
        """A model value below hard_min should be clamped up to hard_min."""
        field = _StubDragField(min_value=0.0, max_value=100.0, hard_min_value=-5.0, hard_max_value=105.0)
        model = MockValueModel(value=-20.0)
        field._clamp_to_hard_bounds(model)
        self.assertEqual(model.get_value_as_float(), -5.0)

    async def test_clamp_above_hard_max(self):
        """A model value above hard_max should be clamped down to hard_max."""
        field = _StubDragField(min_value=0.0, max_value=100.0, hard_min_value=-5.0, hard_max_value=105.0)
        model = MockValueModel(value=200.0)
        field._clamp_to_hard_bounds(model)
        self.assertEqual(model.get_value_as_float(), 105.0)

    async def test_no_clamp_within_hard_bounds(self):
        """A value within hard bounds should not be modified."""
        field = _StubDragField(min_value=0.0, max_value=100.0, hard_min_value=-5.0, hard_max_value=105.0)
        model = MockValueModel(value=50.0)
        field._clamp_to_hard_bounds(model)
        self.assertEqual(model.get_value_as_float(), 50.0)

    async def test_no_clamp_when_hard_bounds_not_set(self):
        """No clamping should occur when neither hard bound is set."""
        field = _StubDragField(min_value=0.0, max_value=100.0)
        model = MockValueModel(value=200.0)
        field._clamp_to_hard_bounds(model)
        self.assertEqual(model.get_value_as_float(), 200.0)

    # ------------------------------------------------------------------
    # Independent hard-bound clamping (single-sided)
    # ------------------------------------------------------------------

    async def test_clamp_with_only_hard_min(self):
        """With only hard_min_value set, values below it should be clamped."""
        field = _StubDragField(hard_min_value=0.0)
        model = MockValueModel(value=-10.0)
        field._clamp_to_hard_bounds(model)
        self.assertEqual(model.get_value_as_float(), 0.0)

    async def test_clamp_with_only_hard_min_no_effect_above(self):
        """With only hard_min_value set, values above it should be untouched."""
        field = _StubDragField(hard_min_value=0.0)
        model = MockValueModel(value=999.0)
        field._clamp_to_hard_bounds(model)
        self.assertEqual(model.get_value_as_float(), 999.0)

    async def test_clamp_with_only_hard_max(self):
        """With only hard_max_value set, values above it should be clamped."""
        field = _StubDragField(hard_max_value=100.0)
        model = MockValueModel(value=200.0)
        field._clamp_to_hard_bounds(model)
        self.assertEqual(model.get_value_as_float(), 100.0)

    async def test_clamp_with_only_hard_max_no_effect_below(self):
        """With only hard_max_value set, values below it should be untouched."""
        field = _StubDragField(hard_max_value=100.0)
        model = MockValueModel(value=-50.0)
        field._clamp_to_hard_bounds(model)
        self.assertEqual(model.get_value_as_float(), -50.0)

    async def test_no_clamp_when_both_hard_bounds_none(self):
        """No clamping when both hard bounds are None."""
        field = _StubDragField()
        model = MockValueModel(value=9999.0)
        field._clamp_to_hard_bounds(model)
        self.assertEqual(model.get_value_as_float(), 9999.0)

    # ------------------------------------------------------------------
    # end_edit integration with hard bounds
    # ------------------------------------------------------------------

    async def test_end_edit_clamps_to_hard_bounds(self):
        """end_edit should clamp out-of-range values to hard bounds."""
        field = _StubDragField(min_value=0.0, max_value=100.0, hard_min_value=0.0, hard_max_value=100.0)
        model = MockValueModel(value=150.0)
        field.end_edit(model)
        self.assertEqual(model.get_value_as_float(), 100.0)

    async def test_end_edit_clamps_single_hard_min(self):
        """end_edit should clamp below hard_min when only hard_min is set."""
        field = _StubDragField(hard_min_value=0.0)
        model = MockValueModel(value=-10.0)
        field.end_edit(model)
        self.assertEqual(model.get_value_as_float(), 0.0)

    async def test_end_edit_clamps_single_hard_max(self):
        """end_edit should clamp above hard_max when only hard_max is set."""
        field = _StubDragField(hard_max_value=100.0)
        model = MockValueModel(value=150.0)
        field.end_edit(model)
        self.assertEqual(model.get_value_as_float(), 100.0)
