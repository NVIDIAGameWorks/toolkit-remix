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

from __future__ import annotations

import asyncio
import contextlib

import carb
import omni.kit.app
import omni.kit.test
import omni.ui as ui
import omni.usd
from omni.flux.property_widget_builder.model.usd import USDAttributeItem, USDDelegate, USDModel
from omni.flux.property_widget_builder.model.usd.setup_ui import USDPropertyWidget
from omni.flux.property_widget_builder.widget import ItemGroup
from omni.flux.utils.widget.color_gradient import ColorGradientWidget
from pxr import Gf, Sdf, Vt


def _attr_path(prim_path: str, name: str) -> Sdf.Path:
    return Sdf.Path(f"{prim_path}.{name}")


def _create_item_group(name: str, children: list) -> ItemGroup:
    group = ItemGroup(name, expanded=True)
    for child in children:
        child.parent = group
    return group


async def _wait(n: int = 5):
    for _ in range(n):
        await omni.kit.app.get_app().next_update_async()


def _find_gradient_and_scalar_rows(delegate):
    """Find the gradient (tall) and scalar (standard) rows from the delegate."""
    gradient_row = None
    scalar_row = None
    for row in delegate._rows.values():
        max_h = 0
        for w in row.attribute_widgets:
            with contextlib.suppress(RuntimeError):
                max_h = max(max_h, w.computed_height)
        if max_h >= ColorGradientWidget.HEIGHT and gradient_row is None:
            gradient_row = row
        elif max_h > 0 and max_h < ColorGradientWidget.HEIGHT and scalar_row is None:
            scalar_row = row
    return gradient_row, scalar_row


def _print_row_diagnostics(label, row):
    carb.log_info(f"{label} row:")
    for i, bg in enumerate(row.override_background_widgets):
        carb.log_info(f"  override_bg[{i}]: y={bg.screen_position_y}, h={bg.computed_height}")
    if row.more_widget:
        carb.log_info(f"  more_widget (M): y={row.more_widget.screen_position_y}, h={row.more_widget.computed_height}")
    if row.default_indicator_widget:
        ci = row.default_indicator_widget
        carb.log_info(f"  default_indicator (circle): y={ci.screen_position_y}, h={ci.computed_height}")
    if row.mixed_indicator_widget:
        mi = row.mixed_indicator_widget
        carb.log_info(f"  mixed_indicator (dots): y={mi.screen_position_y}, h={mi.computed_height}")
    for i, w in enumerate(row.attribute_widgets):
        carb.log_info(f"  attribute_widget[{i}]: y={w.screen_position_y}, h={w.computed_height}")


class TestDelegateAlignment(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        self._stage = self._context.get_stage()

        prim_path = "/World/TestParticle"
        self._prim = self._stage.DefinePrim(prim_path, "Xform")
        self._prim_path = prim_path

        # Gradient attributes (tall rows)
        self._prim.CreateAttribute("primvars:particle:testColor:values", Sdf.ValueTypeNames.Color4fArray).Set(
            Vt.Vec4fArray([Gf.Vec4f(1, 0, 0, 1), Gf.Vec4f(0, 0, 1, 1)])
        )
        self._prim.CreateAttribute("primvars:particle:testColor:times", Sdf.ValueTypeNames.FloatArray).Set(
            Vt.FloatArray([0.0, 1.0])
        )

        # Scalar attributes (standard rows)
        self._prim.CreateAttribute("primvars:particle:mass", Sdf.ValueTypeNames.Float).Set(1.5)
        self._prim.CreateAttribute("primvars:particle:lifetime", Sdf.ValueTypeNames.Float).Set(3.0)

        await _wait(5)

    async def tearDown(self):
        await self._context.close_stage_async()

    async def _build_grouped_property_widget(self):
        """Build a PropertyWidget with grouped items matching the real playground structure."""
        p = self._prim_path

        gradient_items = [
            USDAttributeItem("", [_attr_path(p, "primvars:particle:testColor:values")]),
        ]
        scalar_items = [
            USDAttributeItem("", [_attr_path(p, "primvars:particle:mass")]),
            USDAttributeItem("", [_attr_path(p, "primvars:particle:lifetime")]),
        ]

        animation_group = _create_item_group("Lifetime Animation", gradient_items)
        physics_group = _create_item_group("Physics", scalar_items)

        model = USDModel(context_name="")
        delegate = USDDelegate()

        window = ui.Window("TestDelegateAlignment_Grouped", width=500, height=400)
        with window.frame:
            widget = USDPropertyWidget(context_name="", model=model, delegate=delegate)

        model.set_items([animation_group, physics_group])
        await _wait(15)
        await asyncio.sleep(0.3)
        await _wait(10)

        return window, delegate, model, widget

    async def _build_flat_property_widget(self):
        """Build a PropertyWidget with flat (ungrouped) items."""
        p = self._prim_path

        gradient_item = USDAttributeItem("", [_attr_path(p, "primvars:particle:testColor:values")])
        scalar_item = USDAttributeItem("", [_attr_path(p, "primvars:particle:mass")])

        model = USDModel(context_name="")
        delegate = USDDelegate()

        window = ui.Window("TestDelegateAlignment_Flat", width=500, height=300)
        with window.frame:
            widget = USDPropertyWidget(context_name="", model=model, delegate=delegate)

        model.set_items([gradient_item, scalar_item])
        await _wait(15)
        await asyncio.sleep(0.3)
        await _wait(10)

        return window, delegate, model, widget

    def _assert_top_alignment(self, gradient_row, scalar_row):
        """Assert that branch indicators are top-aligned in the gradient row."""
        carb.log_info("=== ALIGNMENT DIAGNOSTICS ===")
        _print_row_diagnostics("Gradient", gradient_row)
        _print_row_diagnostics("Scalar", scalar_row)
        carb.log_info("=== END DIAGNOSTICS ===")

        # The gradient row's value widget should be taller than standard
        gradient_value_height = max((w.computed_height for w in gradient_row.attribute_widgets), default=0)
        self.assertGreaterEqual(
            gradient_value_height, ColorGradientWidget.HEIGHT, "Gradient value widget should be tall"
        )

        # For each indicator type, check that the Y offset from the row's
        # attribute widget top is similar for gradient and scalar rows.
        # Both rows' attribute_widget[0] starts at the row top.
        for attr_name, label in [
            ("default_indicator_widget", "Default indicator (circle)"),
            ("more_widget", "M badge"),
        ]:
            g_widget = getattr(gradient_row, attr_name, None)
            s_widget = getattr(scalar_row, attr_name, None)
            if not g_widget or not s_widget:
                continue

            g_row_top = (
                gradient_row.attribute_widgets[0].screen_position_y
                if gradient_row.attribute_widgets
                else g_widget.screen_position_y
            )
            s_row_top = (
                scalar_row.attribute_widgets[0].screen_position_y
                if scalar_row.attribute_widgets
                else s_widget.screen_position_y
            )

            g_offset = g_widget.screen_position_y - g_row_top
            s_offset = s_widget.screen_position_y - s_row_top

            carb.log_info(f"{label} - Gradient offset: {g_offset:.1f}, Scalar offset: {s_offset:.1f}")

            self.assertAlmostEqual(
                g_offset,
                s_offset,
                delta=4,
                msg=f"{label} not top-aligned. Gradient offset={g_offset:.1f}, Scalar offset={s_offset:.1f}",
            )

    async def test_branch_indicators_top_aligned_flat(self):
        """Branch indicators should be top-aligned in tall rows (flat items, no groups)."""
        window, delegate, model, widget = await self._build_flat_property_widget()
        try:
            gradient_row, scalar_row = _find_gradient_and_scalar_rows(delegate)
            self.assertIsNotNone(gradient_row, "Could not find gradient row")
            self.assertIsNotNone(scalar_row, "Could not find scalar row")
            self._assert_top_alignment(gradient_row, scalar_row)
        finally:
            widget.destroy()
            window.destroy()

    async def test_branch_indicators_top_aligned_grouped(self):
        """Branch indicators should be top-aligned in tall rows (grouped items matching playground)."""
        window, delegate, model, widget = await self._build_grouped_property_widget()
        try:
            gradient_row, scalar_row = _find_gradient_and_scalar_rows(delegate)
            self.assertIsNotNone(gradient_row, "Could not find gradient row")
            self.assertIsNotNone(scalar_row, "Could not find scalar row")
            self._assert_top_alignment(gradient_row, scalar_row)
        finally:
            widget.destroy()
            window.destroy()
