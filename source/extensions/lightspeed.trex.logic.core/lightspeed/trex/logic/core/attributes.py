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

import json
from typing import Any

import omni.graph.core as og
import omni.graph.tools.ogn as ogn


def _get_type_default(og_type: og.AttributeType) -> Any:
    """Get the default value for an OGN type when no explicit default is defined."""
    # Arrays default to empty list (except string/path which are uchar[])
    if og_type.array_depth > 0:
        if og_type.base_type == og.BaseDataType.UCHAR and og_type.role in (
            og.AttributeRole.TEXT,
            og.AttributeRole.PATH,
        ):
            return ""
        return []

    # Determine base value for the type
    if og_type.base_type == og.BaseDataType.BOOL:
        val_base = False
    elif og_type.base_type == og.BaseDataType.TOKEN:
        val_base = ""
    else:
        val_base = 0

    # Vectors/matrices: expand base value
    if og_type.tuple_count > 1:
        if og_type.role in (
            og.AttributeRole.FRAME,
            og.AttributeRole.MATRIX,
            og.AttributeRole.TRANSFORM,
        ):
            # Identity matrix
            dim = 2 if og_type.tuple_count == 4 else 3 if og_type.tuple_count == 9 else 4
            return [[1 if i == j else 0 for j in range(dim)] for i in range(dim)]
        return [val_base] * og_type.tuple_count

    return val_base


def _ogn_value_to_python_type(value: str, og_type: og.AttributeType) -> Any:
    """Convert an OGN metadata string to a USD-compatible Python type.

    OGN metadata values (defaults, min/max bounds, etc.) are stored as JSON-encoded
    strings in .ogn node definitions. This function deserializes the JSON string back
    into a Python value, then converts it to the appropriate USD type via OmniGraph.

    Args:
        value: The raw metadata string as returned by attr.get_metadata()
               (e.g., "0.5", "100", "[1.0, 2.0, 3.0]").
        og_type: The resolved OmniGraph attribute type, used to select the
                 correct USD type conversion (e.g., float -> float, vec3 -> Gf.Vec3f).

    Returns:
        The value converted to the appropriate USD-compatible Python type.
    """
    py_val = json.loads(value)
    return og.python_value_as_usd(og_type, py_val)


def ogn_read_metadata_key(attr: og.Attribute, key: str):
    """
    Read a single OGN metadata key from an attribute and convert to a Python type.

    Args:
        attr: The OmniGraph attribute to read metadata from.
        key: The metadata key name (e.g. "softMin", "uiStep").

    Returns:
        The metadata value converted to a USD-compatible Python type (e.g. float, int),
        or None if the key is not set.
    """
    val = attr.get_metadata(key)
    if val is None:
        return None

    og_type = attr.get_resolved_type()
    return _ogn_value_to_python_type(val, og_type)


def get_ogn_default_value(attr: og.Attribute) -> Any:
    """Get an OGN attribute's default value as a USD-compatible Python type.

    Uses og.python_value_as_usd() for proper type conversion (Gf.Vec3f, etc.)
    """
    og_type = attr.get_resolved_type()
    default_str = attr.get_metadata(ogn.MetadataKeys.DEFAULT)

    if default_str is not None:
        try:
            return _ogn_value_to_python_type(default_str, og_type)
        except (json.JSONDecodeError, TypeError, ValueError):
            return default_str

    # No explicit default - use type's default value
    py_val = _get_type_default(og_type)
    return og.python_value_as_usd(og_type, py_val)
