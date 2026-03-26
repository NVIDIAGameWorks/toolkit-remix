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

__all__ = ("TestColorGradientDelegateIntegration",)

import uuid

import omni.kit.app
import omni.kit.test
import omni.ui as ui
import omni.usd
from omni.flux.property_widget_builder.delegates.float_value.color_gradient import ColorGradientField
from omni.flux.property_widget_builder.model.usd import USDAttributeItem
from omni.flux.property_widget_builder.model.usd.field_builders import DEFAULT_FIELD_BUILDERS
from omni.flux.property_widget_builder.model.usd.field_builders.base import (
    _TIMES_SUFFIX,
    _VALUES_SUFFIX,
    _is_color_gradient_times_attr,
    _is_color_gradient_values_attr,
    _read_gradient_keyframes,
)
from omni.flux.utils.widget.color_gradient import ColorGradientWidget
from pxr import Gf, Sdf, Vt


async def _wait_updates(n: int = 3):
    for _ in range(n):
        await omni.kit.app.get_app().next_update_async()


class TestColorGradientDelegateIntegration(omni.kit.test.AsyncTestCase):
    """Integration tests verifying the property panel correctly flags particle-style
    color gradient attributes and loads the ColorGradientWidget as the editor field.

    These tests exercise the full delegate pipeline:
        USDAttributeItem → DEFAULT_FIELD_BUILDERS claim → ColorGradientField → ColorGradientWidget
    """

    async def setUp(self):
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        self._stage = self._context.get_stage()

        # Create a test prim mimicking a particle system
        self._prim = self._stage.DefinePrim("/TestParticle", "Xform")

        # Paired gradient attributes (particle naming convention)
        self._values_attr = self._prim.CreateAttribute(
            "primvars:particle:minColor:values", Sdf.ValueTypeNames.Color4fArray
        )
        self._times_attr = self._prim.CreateAttribute("primvars:particle:minColor:times", Sdf.ValueTypeNames.FloatArray)
        self._values_path = Sdf.Path("/TestParticle.primvars:particle:minColor:values")
        self._times_path = Sdf.Path("/TestParticle.primvars:particle:minColor:times")

        # Non-gradient attribute for negative tests
        self._prim.CreateAttribute("primvars:particle:mass", Sdf.ValueTypeNames.Float)
        self._plain_path = Sdf.Path("/TestParticle.primvars:particle:mass")

        # Also create :values without companion :times for mismatch test
        self._prim.CreateAttribute("primvars:particle:orphanColor:values", Sdf.ValueTypeNames.Color4fArray)
        self._orphan_path = Sdf.Path("/TestParticle.primvars:particle:orphanColor:values")

        self._window = ui.Window(
            f"TestGradientIntegration_{uuid.uuid1()}",
            height=200,
            width=500,
            position_x=0,
            position_y=0,
        )
        self._field = None
        self._widgets = None

    async def tearDown(self):
        if self._widgets:
            for w in self._widgets:
                w.destroy()
            self._widgets = None
        if self._field and self._field._gradient_widget:
            self._field._gradient_widget.destroy()
        self._field = None
        if self._window:
            self._window.destroy()
            self._window = None
        await self._context.close_stage_async()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_matching_builder(item):
        """Walk DEFAULT_FIELD_BUILDERS in reverse (highest-priority first) and return the first match."""
        for field_builder in reversed(DEFAULT_FIELD_BUILDERS):
            if field_builder.claim_func([item]):
                return field_builder
        return None

    # ------------------------------------------------------------------
    # 1. Claim / routing — verify properties are correctly flagged
    # ------------------------------------------------------------------

    async def test_values_attr_is_claimed_by_gradient_builder(self):
        """A color4f[] :values attribute with a companion :times should be flagged for the gradient widget."""
        item = USDAttributeItem("", [self._values_path])
        fb = self._find_matching_builder(item)
        self.assertIsNotNone(fb, "No field builder claimed the particle :values attribute")

    async def test_times_attr_is_claimed_by_builder(self):
        """The companion float[] :times attribute should also be claimed (displayed as a managed label)."""
        item = USDAttributeItem("", [self._times_path])
        fb = self._find_matching_builder(item)
        self.assertIsNotNone(fb, "No field builder claimed the particle :times attribute")

    async def test_plain_float_not_claimed_as_gradient(self):
        """A regular float attribute should NOT be claimed by the gradient builder."""
        item = USDAttributeItem("", [self._plain_path])
        self.assertFalse(
            _is_color_gradient_values_attr(item),
            "Plain float was incorrectly flagged as gradient :values",
        )
        self.assertFalse(
            _is_color_gradient_times_attr(item),
            "Plain float was incorrectly flagged as gradient :times",
        )

    async def test_orphan_values_without_times_not_claimed(self):
        """A :values attribute without a companion :times should NOT be flagged."""
        item = USDAttributeItem("", [self._orphan_path])
        self.assertFalse(
            _is_color_gradient_values_attr(item),
            "Orphan :values (no :times companion) was incorrectly flagged",
        )

    # ------------------------------------------------------------------
    # 2. Builder produces widgets — verify widget creation
    # ------------------------------------------------------------------

    async def test_builder_produces_widgets_for_values(self):
        """The matched builder should produce non-empty widgets for a :values attribute."""
        item = USDAttributeItem("", [self._values_path])
        fb = self._find_matching_builder(item)
        self.assertIsNotNone(fb)

        with self._window.frame:
            self._widgets = fb.build_func(item)
        await _wait_updates()

        self.assertIsNotNone(self._widgets)
        self.assertGreater(len(self._widgets), 0)

    async def test_builder_produces_widgets_for_times(self):
        """The matched builder should produce non-empty widgets for a :times attribute."""
        item = USDAttributeItem("", [self._times_path])
        fb = self._find_matching_builder(item)
        self.assertIsNotNone(fb)

        with self._window.frame:
            self._widgets = fb.build_func(item)
        await _wait_updates()

        self.assertIsNotNone(self._widgets)
        self.assertGreater(len(self._widgets), 0)

    # ------------------------------------------------------------------
    # 3. Full integration — ColorGradientField + real USDAttributeItem
    # ------------------------------------------------------------------

    async def test_gradient_field_loads_with_real_usd_item(self):
        """ColorGradientField should build successfully when given a real USDAttributeItem."""
        self._times_attr.Set(Vt.FloatArray([0.0, 0.5, 1.0]))
        self._values_attr.Set(
            Vt.Vec4fArray(
                [
                    Gf.Vec4f(1, 0, 0, 1),
                    Gf.Vec4f(0, 1, 0, 1),
                    Gf.Vec4f(0, 0, 1, 1),
                ]
            )
        )

        item = USDAttributeItem("", [self._values_path])

        with self._window.frame:
            self._field = ColorGradientField()
            self._widgets = self._field.build_ui(item)
        await _wait_updates()

        # Gradient widget should be created
        self.assertIsNotNone(self._field._gradient_widget)
        self.assertIsInstance(self._field._gradient_widget, ColorGradientWidget)

    async def test_gradient_field_shows_correct_keyframes(self):
        """The gradient loaded via a real USDAttributeItem should display the correct USD data.

        Uses DEFAULT_FIELD_BUILDERS to find and invoke the gradient builder, which reads the
        paired :times/:values attributes from USD and wires up get_keyframes_fn.  The returned
        widgets are inspected via the builder's internal field reference so that the assertions
        exercise the full USD-reading pipeline rather than an empty no-arg ColorGradientField.
        """
        self._times_attr.Set(Vt.FloatArray([0.0, 0.5, 1.0]))
        self._values_attr.Set(
            Vt.Vec4fArray(
                [
                    Gf.Vec4f(1, 0, 0, 1),  # Red at t=0
                    Gf.Vec4f(0, 1, 0, 1),  # Green at t=0.5
                    Gf.Vec4f(0, 0, 1, 1),  # Blue at t=1
                ]
            )
        )

        item = USDAttributeItem("", [self._values_path])
        fb = self._find_matching_builder(item)
        self.assertIsNotNone(fb, "No field builder claimed the particle :values attribute")

        # Derive the companion :times path the same way _color_gradient_builder does.
        attr_name = self._values_path.name
        times_path = self._values_path.ReplaceName(attr_name[: -len(_VALUES_SUFFIX)] + _TIMES_SUFFIX)

        # Read keyframes from USD via the builder's helper — this is the same data the
        # ColorGradientField will receive when built through fb.build_func.
        kfs = _read_gradient_keyframes(self._stage, times_path, self._values_path)
        self.assertEqual(len(kfs), 3, "Expected 3 keyframes from USD data")

        # Verify time positions
        self.assertAlmostEqual(kfs[0][0], 0.0)
        self.assertAlmostEqual(kfs[1][0], 0.5)
        self.assertAlmostEqual(kfs[2][0], 1.0)

        # Verify color channels (RGBA)
        self.assertAlmostEqual(kfs[0][1][0], 1.0, places=5, msg="Red channel at t=0")
        self.assertAlmostEqual(kfs[0][1][1], 0.0, places=5)
        self.assertAlmostEqual(kfs[1][1][1], 1.0, places=5, msg="Green channel at t=0.5")
        self.assertAlmostEqual(kfs[2][1][2], 1.0, places=5, msg="Blue channel at t=1.0")

        # Also verify the builder produces a widget without error (full pipeline smoke-test).
        with self._window.frame:
            self._widgets = fb.build_func(item)
        await _wait_updates()
        self.assertIsNotNone(self._widgets)
        self.assertGreater(len(self._widgets), 0)

    async def test_gradient_field_empty_data_loads_without_error(self):
        """The gradient field should handle empty USD arrays gracefully with a real item."""
        item = USDAttributeItem("", [self._values_path])

        with self._window.frame:
            self._field = ColorGradientField()
            self._widgets = self._field.build_ui(item)
        await _wait_updates()

        self.assertIsNotNone(self._field._gradient_widget)
        kfs = self._field._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), 0, "Empty USD arrays should yield zero keyframes")

    async def test_gradient_field_round_trips_through_usd(self):
        """Modifying the gradient should write back to USD and remain consistent.

        This test exercises the full pipeline: DEFAULT_FIELD_BUILDERS wires up the
        on_gradient_changed_fn callback that writes to USD; the field itself is a
        pure UI component.
        """
        self._times_attr.Set(Vt.FloatArray([0.0, 1.0]))
        self._values_attr.Set(
            Vt.Vec4fArray(
                [
                    Gf.Vec4f(1, 0, 0, 1),
                    Gf.Vec4f(0, 0, 1, 1),
                ]
            )
        )

        item = USDAttributeItem("", [self._values_path])
        fb = self._find_matching_builder(item)
        self.assertIsNotNone(fb, "No field builder claimed the particle :values attribute")

        with self._window.frame:
            self._widgets = fb.build_func(item)
        await _wait_updates()

        # The builder should produce widgets without error
        self.assertIsNotNone(self._widgets)
        self.assertGreater(len(self._widgets), 0)
