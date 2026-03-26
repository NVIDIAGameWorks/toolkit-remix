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

Unit tests for FCurveWidget public API additions.

Tests for:
- subscribe_curve_changed() - unified curve change event
- SelectionInfo dataclass - helper properties
- selection property - returns SelectionInfo
- get_selection_tangent_type() - returns common tangent types
- set_selected_keys_tangent_type() - sets tangent type on selected keys
"""

import omni.kit.test
from omni import ui

from omni.flux.fcurve.widget import (
    FCurve,
    FCurveKey,
    FCurveWidget,
    InfinityType,
    KeyReference,
    SelectionInfo,
    TangentType,
)

__all__ = [
    "TestGetSelectionTangentType",
    "TestSelectionInfo",
    "TestSelectionProperty",
    "TestSetSelectedKeysTangentType",
    "TestSubscribeCurveChanged",
]


class TestSelectionInfo(omni.kit.test.AsyncTestCase):
    """Test SelectionInfo dataclass helper properties."""

    async def test_is_empty_when_empty(self):
        """is_empty should be True when no selection."""
        info = SelectionInfo()
        self.assertTrue(info.is_empty)

    async def test_is_empty_with_keys(self):
        """is_empty should be False when keys selected."""
        info = SelectionInfo(keys=[KeyReference("curve1", 0)])
        self.assertFalse(info.is_empty)

    async def test_curve_ids_single_curve(self):
        """curve_ids should return unique curve IDs."""
        info = SelectionInfo(
            keys=[
                KeyReference("curve1", 0),
                KeyReference("curve1", 1),
            ]
        )
        self.assertEqual(info.curve_ids, {"curve1"})

    async def test_curve_ids_multi_curve(self):
        """curve_ids should return all unique curve IDs."""
        info = SelectionInfo(
            keys=[
                KeyReference("curve1", 0),
                KeyReference("curve2", 0),
            ]
        )
        self.assertEqual(info.curve_ids, {"curve1", "curve2"})

    async def test_has_single_key(self):
        """has_single_key should be True for exactly one key."""
        info = SelectionInfo(keys=[KeyReference("curve1", 0)])
        self.assertTrue(info.has_single_key)

        info = SelectionInfo(
            keys=[
                KeyReference("curve1", 0),
                KeyReference("curve1", 1),
            ]
        )
        self.assertFalse(info.has_single_key)

    async def test_key_count(self):
        """key_count should return number of selected keys."""
        info = SelectionInfo(
            keys=[
                KeyReference("curve1", 0),
                KeyReference("curve2", 0),
            ]
        )
        self.assertEqual(info.key_count, 2)


class TestSubscribeCurveChanged(omni.kit.test.AsyncTestCase):
    """Test subscribe_curve_changed() unified event."""

    async def setUp(self):
        self._window = ui.Window("Test", width=400, height=300)
        with self._window.frame:
            self._widget = FCurveWidget()

        self._changed_curve_ids: list[str] = []
        self._sub = self._widget.subscribe_curve_changed(lambda cid: self._changed_curve_ids.append(cid))

        # Set up test curve
        self._widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=0.0, value=0.0),
                        FCurveKey(time=1.0, value=1.0),
                    ],
                )
            }
        )
        self._changed_curve_ids.clear()  # Clear events from set_curves

    async def tearDown(self):
        self._sub = None
        self._widget.destroy()
        self._window.destroy()

    async def test_add_key_fires_event(self):
        """Adding a key should fire curve_changed."""
        self._widget.add_key("test", 0.5, 0.5)

        self.assertEqual(len(self._changed_curve_ids), 1)
        self.assertEqual(self._changed_curve_ids[0], "test")

    async def test_delete_selected_keys_fires_event(self):
        """Deleting keys should fire curve_changed."""
        self._widget.select_keys([KeyReference("test", 0)])
        self._widget.delete_selected_keys()

        self.assertIn("test", self._changed_curve_ids)

    async def test_set_key_tangent_type_fires_event(self):
        """Setting tangent type should fire curve_changed."""
        self._widget.set_key_tangent_type("test", 0, TangentType.FLAT, TangentType.FLAT)

        self.assertEqual(len(self._changed_curve_ids), 1)
        self.assertEqual(self._changed_curve_ids[0], "test")

    async def test_set_curve_infinity_fires_event(self):
        """Setting infinity type should fire curve_changed."""
        self._widget.set_curve_infinity("test", pre_infinity=InfinityType.LINEAR)

        self.assertEqual(len(self._changed_curve_ids), 1)
        self.assertEqual(self._changed_curve_ids[0], "test")


class TestSelectionProperty(omni.kit.test.AsyncTestCase):
    """Test FCurveWidget.selection property."""

    async def setUp(self):
        self._window = ui.Window("Test", width=400, height=300)
        with self._window.frame:
            self._widget = FCurveWidget()

        self._widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(time=0.0, value=0.0),
                        FCurveKey(time=1.0, value=1.0),
                    ],
                )
            }
        )

    async def tearDown(self):
        self._widget.destroy()
        self._window.destroy()

    async def test_selection_returns_selection_info(self):
        """selection property should return SelectionInfo instance."""
        info = self._widget.selection
        self.assertIsInstance(info, SelectionInfo)

    async def test_selection_reflects_selected_keys(self):
        """selection should reflect currently selected keys."""
        self._widget.select_keys([KeyReference("test", 0)])

        info = self._widget.selection
        self.assertEqual(len(info.keys), 1)
        self.assertEqual(info.keys[0].curve_id, "test")
        self.assertEqual(info.keys[0].key_index, 0)


class TestGetSelectionTangentType(omni.kit.test.AsyncTestCase):
    """Test get_selection_tangent_type() method."""

    async def setUp(self):
        self._window = ui.Window("Test", width=400, height=300)
        with self._window.frame:
            self._widget = FCurveWidget()

        self._widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=0.0,
                            value=0.0,
                            in_tangent_type=TangentType.LINEAR,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                        FCurveKey(
                            time=1.0,
                            value=1.0,
                            in_tangent_type=TangentType.LINEAR,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                )
            }
        )

    async def tearDown(self):
        self._widget.destroy()
        self._window.destroy()

    async def test_no_selection_returns_none(self):
        """No selection should return (None, None)."""
        in_type, out_type = self._widget.get_selection_tangent_type()
        self.assertIsNone(in_type)
        self.assertIsNone(out_type)

    async def test_single_key_returns_types(self):
        """Single key selection should return its tangent types."""
        self._widget.select_keys([KeyReference("test", 0)])

        in_type, out_type = self._widget.get_selection_tangent_type()
        self.assertEqual(in_type, TangentType.LINEAR)
        self.assertEqual(out_type, TangentType.LINEAR)

    async def test_mixed_types_returns_none(self):
        """Mixed tangent types should return None."""
        # Change one key's tangent type
        self._widget.set_key_tangent_type("test", 1, TangentType.FLAT, TangentType.FLAT)

        # Select both keys
        self._widget.select_keys(
            [
                KeyReference("test", 0),
                KeyReference("test", 1),
            ]
        )

        in_type, out_type = self._widget.get_selection_tangent_type()
        self.assertIsNone(in_type)  # Mixed: LINEAR vs FLAT
        self.assertIsNone(out_type)


class TestSetSelectedKeysTangentType(omni.kit.test.AsyncTestCase):
    """Test set_selected_keys_tangent_type() method."""

    async def setUp(self):
        self._window = ui.Window("Test", width=400, height=300)
        with self._window.frame:
            self._widget = FCurveWidget()

        self._widget.set_curves(
            {
                "test": FCurve(
                    id="test",
                    keys=[
                        FCurveKey(
                            time=0.0,
                            value=0.0,
                            in_tangent_type=TangentType.LINEAR,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                        FCurveKey(
                            time=1.0,
                            value=1.0,
                            in_tangent_type=TangentType.LINEAR,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                )
            }
        )

    async def tearDown(self):
        self._widget.destroy()
        self._window.destroy()

    async def test_no_selection_returns_zero(self):
        """No selection should return 0 modified."""
        count = self._widget.set_selected_keys_tangent_type(TangentType.FLAT)
        self.assertEqual(count, 0)

    async def test_modifies_selected_keys(self):
        """Should modify tangent type on selected keys."""
        self._widget.select_keys([KeyReference("test", 0)])

        count = self._widget.set_selected_keys_tangent_type(TangentType.FLAT)

        self.assertEqual(count, 1)

        # Verify the tangent type changed
        curve = self._widget.curves["test"]
        self.assertEqual(curve.keys[0].in_tangent_type, TangentType.FLAT)
        self.assertEqual(curve.keys[0].out_tangent_type, TangentType.FLAT)

    async def test_modifies_multiple_keys(self):
        """Should modify all selected keys."""
        self._widget.select_keys(
            [
                KeyReference("test", 0),
                KeyReference("test", 1),
            ]
        )

        count = self._widget.set_selected_keys_tangent_type(TangentType.AUTO)

        self.assertEqual(count, 2)

        curve = self._widget.curves["test"]
        self.assertEqual(curve.keys[0].in_tangent_type, TangentType.AUTO)
        self.assertEqual(curve.keys[1].in_tangent_type, TangentType.AUTO)

    async def test_in_only_flag(self):
        """Should only modify in_tangent when out_tangent=False."""
        self._widget.select_keys([KeyReference("test", 0)])

        self._widget.set_selected_keys_tangent_type(
            TangentType.FLAT,
            in_tangent=True,
            out_tangent=False,
        )

        curve = self._widget.curves["test"]
        self.assertEqual(curve.keys[0].in_tangent_type, TangentType.FLAT)
        self.assertEqual(curve.keys[0].out_tangent_type, TangentType.LINEAR)  # Unchanged

    async def test_fires_curve_changed_event(self):
        """Should fire curve_changed event."""
        changed_ids: list[str] = []
        sub = self._widget.subscribe_curve_changed(lambda cid: changed_ids.append(cid))

        self._widget.select_keys([KeyReference("test", 0)])
        self._widget.set_selected_keys_tangent_type(TangentType.FLAT)

        self.assertIn("test", changed_ids)
        del sub  # Release subscription
