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

import omni.kit.test
import omni.usd
from omni.flux.property_widget_builder.model.usd import USDAttributeItem
from pxr import Sdf


def _make_item(stage, ui_metadata=None, custom_data=None):
    """Helper to create a float attribute and return a USDAttributeItem wrapping it."""
    prim = stage.DefinePrim("/BoundsTestPrim")
    attr = prim.CreateAttribute("testFloat", Sdf.ValueTypeNames.Float)
    attr.Set(0.0)
    if custom_data is not None:
        attr.SetMetadata("customData", custom_data)
    return USDAttributeItem(
        context_name="",
        attribute_paths=[Sdf.Path("/BoundsTestPrim.testFloat")],
        ui_metadata=ui_metadata,
    )


class TestUSDAttributeItemBounds(omni.kit.test.AsyncTestCase):
    """Tests for the updated get_min_max_bounds / _get_min_max_from_ui_metadata logic."""

    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()

    async def tearDown(self):
        if self.context:
            await self.context.close_stage_async()
        self.context = None
        self.stage = None

    # ------------------------------------------------------------------
    # _get_min_max_from_ui_metadata tests
    # ------------------------------------------------------------------

    async def test_ui_metadata_soft_and_hard_bounds(self):
        """All four keys present: returns (soft_min, soft_max, hard_min, hard_max)."""
        item = _make_item(
            self.stage,
            ui_metadata={
                "soft_min": 0.0,
                "soft_max": 100.0,
                "hard_min": -10.0,
                "hard_max": 110.0,
            },
        )
        result = item._get_min_max_from_ui_metadata()
        self.assertEqual(result, (0.0, 100.0, -10.0, 110.0))

    async def test_ui_metadata_soft_only(self):
        """Only soft bounds: returns (soft_min, soft_max, None, None)."""
        item = _make_item(
            self.stage,
            ui_metadata={
                "soft_min": 5.0,
                "soft_max": 50.0,
            },
        )
        result = item._get_min_max_from_ui_metadata()
        self.assertEqual(result, (5.0, 50.0, None, None))

    async def test_ui_metadata_hard_only(self):
        """Only hard bounds: hard values fill in for min/max."""
        item = _make_item(
            self.stage,
            ui_metadata={
                "hard_min": -20.0,
                "hard_max": 200.0,
            },
        )
        result = item._get_min_max_from_ui_metadata()
        self.assertEqual(result, (-20.0, 200.0, -20.0, 200.0))

    async def test_ui_metadata_min_only_soft(self):
        """Only soft_min present: returns (soft_min, None, None, None)."""
        item = _make_item(
            self.stage,
            ui_metadata={
                "soft_min": 0.0,
            },
        )
        result = item._get_min_max_from_ui_metadata()
        self.assertEqual(result, (0.0, None, None, None))

    async def test_ui_metadata_max_only_soft(self):
        """Only soft_max present: returns (None, soft_max, None, None)."""
        item = _make_item(
            self.stage,
            ui_metadata={
                "soft_max": 100.0,
            },
        )
        result = item._get_min_max_from_ui_metadata()
        self.assertEqual(result, (None, 100.0, None, None))

    async def test_ui_metadata_min_only_hard(self):
        """Only hard_min present: hard_min fills in for min."""
        item = _make_item(
            self.stage,
            ui_metadata={
                "hard_min": -5.0,
            },
        )
        result = item._get_min_max_from_ui_metadata()
        self.assertEqual(result, (-5.0, None, -5.0, None))

    async def test_ui_metadata_max_only_hard(self):
        """Only hard_max present: hard_max fills in for max."""
        item = _make_item(
            self.stage,
            ui_metadata={
                "hard_max": 200.0,
            },
        )
        result = item._get_min_max_from_ui_metadata()
        self.assertEqual(result, (None, 200.0, None, 200.0))

    async def test_ui_metadata_none_returns_none(self):
        """No ui_metadata at all: returns None."""
        item = _make_item(self.stage, ui_metadata=None)
        result = item._get_min_max_from_ui_metadata()
        self.assertIsNone(result)

    async def test_ui_metadata_empty_dict_returns_none(self):
        """Empty ui_metadata dict (no bound keys): returns None."""
        item = _make_item(self.stage, ui_metadata={})
        result = item._get_min_max_from_ui_metadata()
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # _get_min_max_from_attr_metadata tests (customData on USD attribute)
    # ------------------------------------------------------------------

    async def test_attr_metadata_both_bounds(self):
        """customData range with both min and max: returns (min, max, None, None)."""
        item = _make_item(self.stage, custom_data={"range": {"min": 0.0, "max": 100.0}})
        result = item._get_min_max_from_attr_metadata()
        self.assertEqual(result, (0.0, 100.0, None, None))

    async def test_attr_metadata_min_only(self):
        """customData range with only min: returns (min, None, None, None)."""
        item = _make_item(self.stage, custom_data={"range": {"min": 0.0}})
        result = item._get_min_max_from_attr_metadata()
        self.assertEqual(result, (0.0, None, None, None))

    async def test_attr_metadata_max_only(self):
        """customData range with only max: returns (None, max, None, None)."""
        item = _make_item(self.stage, custom_data={"range": {"max": 100.0}})
        result = item._get_min_max_from_attr_metadata()
        self.assertEqual(result, (None, 100.0, None, None))

    async def test_attr_metadata_no_range(self):
        """customData without range key: returns None."""
        item = _make_item(self.stage, custom_data={"other_key": "value"})
        result = item._get_min_max_from_attr_metadata()
        self.assertIsNone(result)

    async def test_attr_metadata_no_custom_data(self):
        """No customData at all: returns None."""
        item = _make_item(self.stage)
        result = item._get_min_max_from_attr_metadata()
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # get_min_max_bounds integration (ui_metadata takes priority)
    # ------------------------------------------------------------------

    async def test_get_min_max_bounds_prefers_ui_metadata(self):
        """ui_metadata should take priority over attr customData."""
        item = _make_item(
            self.stage,
            ui_metadata={"soft_min": 10.0, "soft_max": 90.0},
            custom_data={"range": {"min": 0.0, "max": 100.0}},
        )
        result = item.get_min_max_bounds()
        self.assertEqual(result, (10.0, 90.0, None, None))

    async def test_get_min_max_bounds_falls_back_to_attr(self):
        """When ui_metadata has no bounds, attr customData is used."""
        item = _make_item(
            self.stage,
            ui_metadata={},
            custom_data={"range": {"min": 0.0, "max": 100.0}},
        )
        result = item.get_min_max_bounds()
        self.assertEqual(result, (0.0, 100.0, None, None))

    async def test_get_min_max_bounds_returns_none_when_no_data(self):
        """No bounds anywhere: returns None."""
        item = _make_item(self.stage)
        result = item.get_min_max_bounds()
        self.assertIsNone(result)
