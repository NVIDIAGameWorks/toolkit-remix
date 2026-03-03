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

__all__ = ("TestAbstractValueFieldUnit",)

import omni.kit.test
import omni.ui as ui
from omni.flux.property_widget_builder.delegates.base import AbstractValueField

from .mocks import MockValueModel


class _StubValueField(AbstractValueField):
    """Thin concrete subclass for testing AbstractValueField logic."""

    def __init__(self, **kwargs):
        kwargs.setdefault("widget_type", ui.FloatField)
        kwargs.setdefault("style_name", "StubValueField")
        super().__init__(**kwargs)

    def _get_value_from_model(self, model) -> float:
        return model.get_value_as_float()


class TestAbstractValueFieldUnit(omni.kit.test.AsyncTestCase):
    # ------------------------------------------------------------------
    # Constructor tests
    # ------------------------------------------------------------------

    async def test_stores_widget_type_and_clamp_bounds(self):
        """Constructor should persist widget_type, clamp_min, and clamp_max."""
        field = _StubValueField(widget_type=ui.FloatField, clamp_min=-10.0, clamp_max=10.0)
        self.assertEqual(field.widget_type, ui.FloatField)
        self.assertEqual(field.clamp_min, -10.0)
        self.assertEqual(field.clamp_max, 10.0)

    async def test_clamp_bounds_default_none(self):
        """clamp_min and clamp_max should default to None."""
        field = _StubValueField()
        self.assertIsNone(field.clamp_min)
        self.assertIsNone(field.clamp_max)

    # ------------------------------------------------------------------
    # _clamp tests
    # ------------------------------------------------------------------

    async def test_clamp_below_min(self):
        """A model value below clamp_min should be clamped up."""
        field = _StubValueField(clamp_min=0.0, clamp_max=100.0)
        model = MockValueModel(value=-5.0)
        field._clamp(model)
        self.assertEqual(model.get_value_as_float(), 0.0)

    async def test_clamp_above_max(self):
        """A model value above clamp_max should be clamped down."""
        field = _StubValueField(clamp_min=0.0, clamp_max=100.0)
        model = MockValueModel(value=150.0)
        field._clamp(model)
        self.assertEqual(model.get_value_as_float(), 100.0)

    async def test_no_clamp_within_range(self):
        """A value within bounds should not be modified."""
        field = _StubValueField(clamp_min=0.0, clamp_max=100.0)
        model = MockValueModel(value=50.0)
        field._clamp(model)
        self.assertEqual(model.get_value_as_float(), 50.0)

    async def test_clamp_with_only_min(self):
        """One-sided min clamping: values below clamp_min are clamped, no upper bound."""
        field = _StubValueField(clamp_min=0.0)
        model = MockValueModel(value=-10.0)
        field._clamp(model)
        self.assertEqual(model.get_value_as_float(), 0.0)

    async def test_clamp_with_only_min_no_effect_above(self):
        """One-sided min clamping: values above clamp_min are untouched."""
        field = _StubValueField(clamp_min=0.0)
        model = MockValueModel(value=999.0)
        field._clamp(model)
        self.assertEqual(model.get_value_as_float(), 999.0)

    async def test_clamp_with_only_max(self):
        """One-sided max clamping: values above clamp_max are clamped, no lower bound."""
        field = _StubValueField(clamp_max=100.0)
        model = MockValueModel(value=200.0)
        field._clamp(model)
        self.assertEqual(model.get_value_as_float(), 100.0)

    async def test_clamp_with_only_max_no_effect_below(self):
        """One-sided max clamping: values below clamp_max are untouched."""
        field = _StubValueField(clamp_max=100.0)
        model = MockValueModel(value=-50.0)
        field._clamp(model)
        self.assertEqual(model.get_value_as_float(), -50.0)

    async def test_no_clamp_when_both_none(self):
        """No clamping when both clamp_min and clamp_max are None."""
        field = _StubValueField()
        model = MockValueModel(value=9999.0)
        field._clamp(model)
        self.assertEqual(model.get_value_as_float(), 9999.0)

    # ------------------------------------------------------------------
    # end_edit integration
    # ------------------------------------------------------------------

    async def test_end_edit_clamps_value(self):
        """end_edit should clamp out-of-range values."""
        field = _StubValueField(clamp_min=0.0, clamp_max=100.0)
        model = MockValueModel(value=150.0)
        field.end_edit(model)
        self.assertEqual(model.get_value_as_float(), 100.0)
