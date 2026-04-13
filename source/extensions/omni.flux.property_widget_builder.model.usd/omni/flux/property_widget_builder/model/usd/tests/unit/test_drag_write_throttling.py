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
from omni.flux.property_widget_builder.model.usd.item_model.attr_value import UsdAttributeValueModel
from pxr import Sdf


def _make_model(stage, value=0.0):
    prim = stage.DefinePrim("/DragTestPrim")
    attr = prim.CreateAttribute("testFloat", Sdf.ValueTypeNames.Float)
    attr.Set(value)
    return UsdAttributeValueModel(
        context_name="",
        attribute_paths=[Sdf.Path("/DragTestPrim.testFloat")],
        channel_index=0,
    )


def _usd_value(stage):
    return stage.GetPrimAtPath("/DragTestPrim").GetAttribute("testFloat").Get()


class TestDragWriteThrottling(omni.kit.test.AsyncTestCase):
    """Regression tests for deferred drag writes in UsdAttributeValueModel."""

    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()

    async def tearDown(self):
        if self.context:
            await self.context.close_stage_async()
        self.context = None
        self.stage = None

    async def test_begin_edit_does_not_start_drag_batching(self):
        # Arrange
        model = _make_model(self.stage)

        # Act
        model.begin_edit()

        # Assert
        self.assertFalse(model.is_batch_editing)

    async def test_set_value_outside_batch_edit_writes_immediately(self):
        # Arrange
        model = _make_model(self.stage, value=0.0)

        # Act
        model.set_value(42.0)

        # Assert
        self.assertAlmostEqual(_usd_value(self.stage), 42.0)

    async def test_set_value_during_batch_edit_updates_only_cached_value(self):
        # Arrange
        model = _make_model(self.stage, value=0.0)

        with patch("omni.kit.undo.begin_group"), patch("omni.kit.undo.end_group"):
            model.begin_batch_edit()

            # Act
            model.set_value(5.0)

            # Assert
            self.assertAlmostEqual(model.get_value_as_float(), 5.0)
            self.assertAlmostEqual(_usd_value(self.stage), 0.0)

    async def test_end_batch_edit_flushes_only_the_final_drag_value(self):
        # Arrange
        model = _make_model(self.stage, value=0.0)

        with patch("omni.kit.undo.begin_group") as begin_group, patch("omni.kit.undo.end_group") as end_group:
            model.begin_batch_edit()
            model.set_value(10.0)
            self.assertAlmostEqual(_usd_value(self.stage), 0.0)
            model.set_value(20.0)
            self.assertAlmostEqual(_usd_value(self.stage), 0.0)
            model.set_value(30.0)
            self.assertAlmostEqual(_usd_value(self.stage), 0.0)

            # Act
            model.end_batch_edit()

            # Assert
            begin_group.assert_called_once_with()
            end_group.assert_called_once_with()
            self.assertAlmostEqual(_usd_value(self.stage), 30.0)
