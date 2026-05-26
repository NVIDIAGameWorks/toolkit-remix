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

from unittest.mock import patch

import omni.kit.test
import omni.usd
from omni.flux.property_widget_builder.model.usd.field_builders.gradient import UsdColorGradientWidget
from pxr import Gf, Sdf, Vt


class TestUsdGradientWidgetDragLifecycle(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        self._stage = self._context.get_stage()
        self._prim_path = "/World/TestGradient"
        self._base_name = "primvars:test"
        self._widget = None

        prim = self._stage.DefinePrim(self._prim_path, "Xform")
        prim.CreateAttribute(f"{self._base_name}:times", Sdf.ValueTypeNames.DoubleArray).Set(Vt.DoubleArray([0.0, 1.0]))
        prim.CreateAttribute(f"{self._base_name}:values", Sdf.ValueTypeNames.Color4fArray).Set(
            Vt.Vec4fArray([Gf.Vec4f(1, 0, 0, 1), Gf.Vec4f(0, 0, 1, 1)])
        )

    async def tearDown(self):
        if self._widget is not None:
            self._widget.destroy()
            self._widget = None
        await self._context.close_stage_async()

    async def test_noop_drag_end_does_not_create_gradient_command(self):
        # Arrange
        self._widget = UsdColorGradientWidget("", self._prim_path, self._base_name)
        self._widget._on_usd_drag_started()

        # Act
        with patch(
            "omni.flux.property_widget_builder.model.usd.field_builders.gradient.omni.kit.commands.execute"
        ) as execute:
            self._widget._on_usd_drag_ended()

        # Assert
        execute.assert_not_called()
