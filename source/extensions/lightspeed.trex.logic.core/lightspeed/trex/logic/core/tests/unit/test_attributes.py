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
import omni.graph.tools.ogn as ogn
import omni.kit.test
from lightspeed.trex.logic.core.attributes import get_ogn_default_value


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


class TestGetOgnDefaultValue(omni.kit.test.AsyncTestCase):
    """Tests for get_ogn_default_value().

    setUp patches og.python_value_as_usd as a passthrough by default.
    Tests that need a different side_effect (e.g. raising an exception)
    can reconfigure self.mock_python_value_as_usd directly.
    """

    async def setUp(self):
        self._patcher = patch.object(og, "python_value_as_usd", side_effect=lambda t, v: v)
        self.mock_python_value_as_usd = self._patcher.start()

    async def tearDown(self):
        self._patcher.stop()

    # ------------------------------------------------------------------
    # Explicit default metadata path
    # ------------------------------------------------------------------

    async def test_returns_converted_default_when_metadata_exists(self):
        """When DEFAULT metadata is set, should JSON-decode and convert it."""
        og_type = _make_og_type(base_type=og.BaseDataType.FLOAT)
        attr = _make_attr(
            og_type=og_type,
            metadata={ogn.MetadataKeys.DEFAULT: "3.14"},
        )

        result = get_ogn_default_value(attr)
        self.assertAlmostEqual(result, 3.14)

    async def test_returns_raw_string_on_json_decode_error(self):
        """When DEFAULT metadata is invalid JSON, should return the raw string."""
        og_type = _make_og_type()
        attr = _make_attr(
            og_type=og_type,
            metadata={ogn.MetadataKeys.DEFAULT: "not{json"},
        )

        result = get_ogn_default_value(attr)
        self.assertEqual(result, "not{json")

    async def test_returns_raw_string_on_type_error(self):
        """When python_value_as_usd raises TypeError, should return the raw string."""
        self.mock_python_value_as_usd.side_effect = TypeError("bad type")

        og_type = _make_og_type()
        attr = _make_attr(
            og_type=og_type,
            metadata={ogn.MetadataKeys.DEFAULT: "42"},
        )

        result = get_ogn_default_value(attr)
        self.assertEqual(result, "42")

    async def test_returns_raw_string_on_value_error(self):
        """When python_value_as_usd raises ValueError, should return the raw string."""
        self.mock_python_value_as_usd.side_effect = ValueError("bad value")

        og_type = _make_og_type()
        attr = _make_attr(
            og_type=og_type,
            metadata={ogn.MetadataKeys.DEFAULT: '"hello"'},
        )

        result = get_ogn_default_value(attr)
        self.assertEqual(result, '"hello"')

    # ------------------------------------------------------------------
    # No default metadata — fallback to type defaults
    # ------------------------------------------------------------------

    async def test_fallback_scalar_float(self):
        """A scalar float with no default should yield 0."""
        og_type = _make_og_type(base_type=og.BaseDataType.FLOAT)
        attr = _make_attr(og_type=og_type, metadata={})

        result = get_ogn_default_value(attr)
        self.assertEqual(result, 0)

    async def test_fallback_bool(self):
        """A scalar bool with no default should yield False."""
        og_type = _make_og_type(base_type=og.BaseDataType.BOOL)
        attr = _make_attr(og_type=og_type, metadata={})

        result = get_ogn_default_value(attr)
        self.assertFalse(result)

    async def test_fallback_token(self):
        """A scalar token with no default should yield empty string."""
        og_type = _make_og_type(base_type=og.BaseDataType.TOKEN)
        attr = _make_attr(og_type=og_type, metadata={})

        result = get_ogn_default_value(attr)
        self.assertEqual(result, "")

    async def test_fallback_array(self):
        """A generic array type with no default should yield empty list."""
        og_type = _make_og_type(base_type=og.BaseDataType.FLOAT, array_depth=1)
        attr = _make_attr(og_type=og_type, metadata={})

        result = get_ogn_default_value(attr)
        self.assertEqual(result, [])

    async def test_fallback_uchar_text_array(self):
        """A UCHAR array with TEXT role (i.e. string) should yield empty string."""
        og_type = _make_og_type(
            base_type=og.BaseDataType.UCHAR,
            role=og.AttributeRole.TEXT,
            array_depth=1,
        )
        attr = _make_attr(og_type=og_type, metadata={})

        result = get_ogn_default_value(attr)
        self.assertEqual(result, "")

    async def test_fallback_uchar_path_array(self):
        """A UCHAR array with PATH role should yield empty string."""
        og_type = _make_og_type(
            base_type=og.BaseDataType.UCHAR,
            role=og.AttributeRole.PATH,
            array_depth=1,
        )
        attr = _make_attr(og_type=og_type, metadata={})

        result = get_ogn_default_value(attr)
        self.assertEqual(result, "")

    async def test_fallback_vector3(self):
        """A 3-component vector with no default should yield [0, 0, 0]."""
        og_type = _make_og_type(
            base_type=og.BaseDataType.FLOAT,
            tuple_count=3,
        )
        attr = _make_attr(og_type=og_type, metadata={})

        result = get_ogn_default_value(attr)
        self.assertEqual(result, [0, 0, 0])

    async def test_fallback_matrix_3x3_identity(self):
        """A 3x3 matrix (tuple_count=9) with MATRIX role should yield 3x3 identity."""
        og_type = _make_og_type(
            base_type=og.BaseDataType.DOUBLE,
            role=og.AttributeRole.MATRIX,
            tuple_count=9,
        )
        attr = _make_attr(og_type=og_type, metadata={})

        result = get_ogn_default_value(attr)
        expected = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        self.assertEqual(result, expected)

    async def test_fallback_matrix_4x4_identity(self):
        """A 4x4 matrix (tuple_count=16) with FRAME role should yield 4x4 identity."""
        og_type = _make_og_type(
            base_type=og.BaseDataType.DOUBLE,
            role=og.AttributeRole.FRAME,
            tuple_count=16,
        )
        attr = _make_attr(og_type=og_type, metadata={})

        result = get_ogn_default_value(attr)
        expected = [
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ]
        self.assertEqual(result, expected)

    async def test_fallback_matrix_2x2_identity(self):
        """A 2x2 matrix (tuple_count=4) with TRANSFORM role should yield 2x2 identity."""
        og_type = _make_og_type(
            base_type=og.BaseDataType.DOUBLE,
            role=og.AttributeRole.TRANSFORM,
            tuple_count=4,
        )
        attr = _make_attr(og_type=og_type, metadata={})

        result = get_ogn_default_value(attr)
        expected = [[1, 0], [0, 1]]
        self.assertEqual(result, expected)
