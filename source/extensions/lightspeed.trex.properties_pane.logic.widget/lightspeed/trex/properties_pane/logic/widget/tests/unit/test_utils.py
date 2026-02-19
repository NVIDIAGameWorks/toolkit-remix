"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from unittest.mock import MagicMock, patch

import omni.graph.core as og
import omni.kit.test
from lightspeed.trex.properties_pane.logic.widget.utils import get_ogn_ui_metadata


def _make_og_type(
    base_type=og.BaseDataType.FLOAT,
    role=og.AttributeRole.NONE,
    array_depth=0,
    tuple_count=1,
):
    """Create a mock og.AttributeType with the specified properties."""
    og_type = MagicMock(spec=og.AttributeType)
    og_type.base_type = base_type
    og_type.role = role
    og_type.array_depth = array_depth
    og_type.tuple_count = tuple_count
    return og_type


def _make_attr(og_type=None, metadata=None):
    """Create a mock og.Attribute with the specified resolved type and metadata lookup.

    Args:
        og_type: The og.AttributeType to return from get_resolved_type() and get_type_name().
        metadata: dict mapping metadata keys to string values (or None).
    """
    resolved = og_type or _make_og_type()
    attr = MagicMock(spec=og.Attribute)
    attr.get_resolved_type.return_value = resolved
    attr.get_type_name.return_value = resolved
    metadata = metadata or {}
    attr.get_metadata.side_effect = lambda key: metadata.get(key)
    return attr


class TestGetOgnUiMetadata(omni.kit.test.AsyncTestCase):
    """Tests for get_ogn_ui_metadata()."""

    async def test_returns_dict_with_all_five_keys(self):
        """Should return a dict with soft_min, soft_max, hard_min, hard_max, ui_step."""
        attr = _make_attr(metadata={})
        result = get_ogn_ui_metadata(attr)
        self.assertEqual(
            set(result.keys()),
            {"soft_min", "soft_max", "hard_min", "hard_max", "ui_step"},
        )

    async def test_missing_metadata_yields_none(self):
        """Keys with no metadata should be None."""
        attr = _make_attr(metadata={})
        result = get_ogn_ui_metadata(attr)
        for v in result.values():
            self.assertIsNone(v)

    async def test_converts_set_metadata_values(self):
        """Keys with OGN metadata should have converted (float/int) values."""
        og_type = _make_og_type(base_type=og.BaseDataType.FLOAT)
        attr = _make_attr(
            og_type=og_type,
            metadata={
                "softMin": "0.0",
                "softMax": "100.0",
                "hardMin": "-10.0",
                "hardMax": "110.0",
                "uiStep": "1.0",
            },
        )
        with patch.object(og, "python_value_as_usd", side_effect=lambda t, v: v):
            result = get_ogn_ui_metadata(attr)
        self.assertEqual(result["soft_min"], 0.0)
        self.assertEqual(result["soft_max"], 100.0)
        self.assertEqual(result["hard_min"], -10.0)
        self.assertEqual(result["hard_max"], 110.0)
        self.assertEqual(result["ui_step"], 1.0)

    async def test_partial_metadata(self):
        """Only set keys should have values; others should be None."""
        og_type = _make_og_type(base_type=og.BaseDataType.FLOAT)
        attr = _make_attr(
            og_type=og_type,
            metadata={"softMin": "0.5", "softMax": "2.5"},
        )
        with patch.object(og, "python_value_as_usd", side_effect=lambda t, v: v):
            result = get_ogn_ui_metadata(attr)
        self.assertEqual(result["soft_min"], 0.5)
        self.assertEqual(result["soft_max"], 2.5)
        self.assertIsNone(result["hard_min"])
        self.assertIsNone(result["hard_max"])
        self.assertIsNone(result["ui_step"])
