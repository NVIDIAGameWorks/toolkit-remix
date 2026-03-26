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


Manual playground showing the full property panel with dummy particle attributes.

This exercises the entire delegate pipeline (USD stage -> USDAttributeItem ->
field_builder claim -> ColorGradientField / DefaultField / DefaultLabelField)
inside a real PropertyWidget tree, so you can visually verify:

  * Compact gradient widget sizing relative to normal property rows
  * Selection highlighting / background blending
  * Gradient bar, markers, and edit-row controls

Run with (from repo root):
    ./_build/windows-x86_64/release/kit/kit.exe ^
        --enable omni.flux.property_widget_builder.model.usd ^
        --ext-folder "./_build/windows-x86_64/release/exts" ^
        --ext-folder "./_build/windows-x86_64/release/extscache" ^
        --portable-root "./_build/windows-x86_64/release" ^
        --exec "source/extensions/omni.flux.property_widget_builder.delegates/bin/manual_property_panel_playground.py"
"""

import asyncio

import omni.kit.app
import omni.ui as ui
import omni.usd
from omni.flux.property_widget_builder.model.usd import USDAttributeItem, USDDelegate, USDModel
from omni.flux.property_widget_builder.model.usd.setup_ui import USDPropertyWidget
from omni.flux.property_widget_builder.widget import ItemGroup
from pxr import Gf, Sdf, Vt


def _attr_path(prim_path: str, name: str) -> Sdf.Path:
    return Sdf.Path(f"{prim_path}.{name}")


def _create_item_group(name: str, children: list) -> ItemGroup:
    """Create a collapsible group (expanded by default) with the given children."""
    group = ItemGroup(name, expanded=True)
    for child in children:
        child.parent = group
    return group


async def main():
    print("=" * 80)
    print("Property Panel Playground — Particle Gradient Attributes")
    print("=" * 80)
    print()
    print("This window shows a full PropertyWidget tree with dummy particle")
    print("attributes so you can verify the gradient widget integration.")
    print()
    print("Close the window when done.")
    print("=" * 80)

    # ------------------------------------------------------------------
    # 1. Create a new USD stage with dummy particle attributes
    # ------------------------------------------------------------------
    context = omni.usd.get_context()
    await context.new_stage_async()
    stage = context.get_stage()

    prim_path = "/World/ParticleSystem"
    prim = stage.DefinePrim(prim_path, "Xform")

    # --- Gradient pairs: color4f[] :values + float[] :times ---------------

    # Min Color gradient (Red -> Green -> Blue)
    prim.CreateAttribute("primvars:particle:minColor:values", Sdf.ValueTypeNames.Color4fArray).Set(
        Vt.Vec4fArray(
            [
                Gf.Vec4f(1, 0, 0, 1),
                Gf.Vec4f(0, 1, 0, 1),
                Gf.Vec4f(0, 0, 1, 1),
            ]
        )
    )
    prim.CreateAttribute("primvars:particle:minColor:times", Sdf.ValueTypeNames.FloatArray).Set(
        Vt.FloatArray([0.0, 0.5, 1.0])
    )

    # Max Color gradient (Yellow -> Cyan)
    prim.CreateAttribute("primvars:particle:maxColor:values", Sdf.ValueTypeNames.Color4fArray).Set(
        Vt.Vec4fArray(
            [
                Gf.Vec4f(1, 1, 0, 1),
                Gf.Vec4f(0, 1, 1, 1),
            ]
        )
    )
    prim.CreateAttribute("primvars:particle:maxColor:times", Sdf.ValueTypeNames.FloatArray).Set(
        Vt.FloatArray([0.0, 1.0])
    )

    # Alpha gradient (transparent -> opaque -> transparent)
    prim.CreateAttribute("primvars:particle:alpha:values", Sdf.ValueTypeNames.Color4fArray).Set(
        Vt.Vec4fArray(
            [
                Gf.Vec4f(1, 1, 1, 0),
                Gf.Vec4f(1, 1, 1, 0.5),
                Gf.Vec4f(1, 1, 1, 1),
                Gf.Vec4f(1, 1, 1, 0),
            ]
        )
    )
    prim.CreateAttribute("primvars:particle:alpha:times", Sdf.ValueTypeNames.FloatArray).Set(
        Vt.FloatArray([0.0, 0.3, 0.7, 1.0])
    )

    # --- Regular (non-gradient) scalar attributes for comparison ----------

    prim.CreateAttribute("primvars:particle:mass", Sdf.ValueTypeNames.Float).Set(1.5)
    prim.CreateAttribute("primvars:particle:lifetime", Sdf.ValueTypeNames.Float).Set(3.0)
    prim.CreateAttribute("primvars:particle:drag", Sdf.ValueTypeNames.Float).Set(0.05)
    prim.CreateAttribute("primvars:particle:initialVelocity", Sdf.ValueTypeNames.Float3).Set(Gf.Vec3f(0, 5, 0))

    # A color3f attribute (NOT a gradient — uses the standard ColorField)
    prim.CreateAttribute("primvars:particle:emissionColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(1.0, 0.4, 0.1))

    # Wait for USD to settle
    for _ in range(5):
        await omni.kit.app.get_app().next_update_async()

    # ------------------------------------------------------------------
    # 2. Build USDAttributeItem list
    # ------------------------------------------------------------------
    p = prim_path  # shorthand

    # Gradient items (grouped under "Lifetime Animation")
    # Only list the :values attributes — the ColorGradientField delegate
    # automatically reads the companion :times attribute from USD.
    gradient_items = [
        USDAttributeItem("", [_attr_path(p, "primvars:particle:minColor:values")]),
        USDAttributeItem("", [_attr_path(p, "primvars:particle:maxColor:values")]),
        USDAttributeItem("", [_attr_path(p, "primvars:particle:alpha:values")]),
    ]

    # Scalar items (grouped under "Physics")
    scalar_items = [
        USDAttributeItem("", [_attr_path(p, "primvars:particle:mass")]),
        USDAttributeItem("", [_attr_path(p, "primvars:particle:lifetime")]),
        USDAttributeItem("", [_attr_path(p, "primvars:particle:drag")]),
        USDAttributeItem("", [_attr_path(p, "primvars:particle:initialVelocity")]),
        USDAttributeItem("", [_attr_path(p, "primvars:particle:emissionColor")]),
    ]

    # Use ItemGroup to organize — mimics the real Remix property panel sections
    animation_group = _create_item_group("Lifetime Animation", gradient_items)
    physics_group = _create_item_group("Physics", scalar_items)

    # ------------------------------------------------------------------
    # 3. Create the property panel
    # ------------------------------------------------------------------
    window = ui.Window(
        "Property Panel Playground - Particles",
        width=550,
        height=600,
    )

    model = USDModel(context_name="")
    delegate = USDDelegate()

    with window.frame:
        property_widget = USDPropertyWidget(
            context_name="",
            model=model,
            delegate=delegate,
        )

    model.set_items([animation_group, physics_group])

    # Let the tree widget settle
    for _ in range(10):
        await omni.kit.app.get_app().next_update_async()

    print("\nProperty panel is ready! Interact with the gradient widgets.")
    print("Close the window when done.\n")

    # Keep alive until user closes the window
    while window.visible:
        await omni.kit.app.get_app().next_update_async()

    print("\nPlayground window closed.")
    property_widget.destroy()
    window.destroy()


if __name__ == "__main__":
    asyncio.ensure_future(main())
