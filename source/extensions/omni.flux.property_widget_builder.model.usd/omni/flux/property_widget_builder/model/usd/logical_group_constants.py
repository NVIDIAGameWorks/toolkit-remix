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

from .logical_row import LogicalGroupDefinition

__all__ = [
    "CURVE_LOGICAL_GROUP_DEFINITION",
    "CURVE_LOGICAL_SUFFIXES",
    "GRADIENT_LOGICAL_GROUP_DEFINITION",
    "GRADIENT_LOGICAL_SUFFIXES",
    "PRIMVAR_PREFIX",
    "SCALAR_CURVE_LOGICAL_GROUP_DEFINITION",
    "SCALAR_CURVE_LOGICAL_SUFFIXES",
]

PRIMVAR_PREFIX = "primvars:"

_KEYED_VALUE_SUFFIXES = frozenset({"times", "values"})

GRADIENT_LOGICAL_SUFFIXES = _KEYED_VALUE_SUFFIXES
GRADIENT_LOGICAL_GROUP_DEFINITION = LogicalGroupDefinition(
    suffixes=tuple(sorted(GRADIENT_LOGICAL_SUFFIXES)),
    widget_kind="gradient",
)

SCALAR_CURVE_LOGICAL_SUFFIXES = _KEYED_VALUE_SUFFIXES
SCALAR_CURVE_LOGICAL_GROUP_DEFINITION = LogicalGroupDefinition(
    suffixes=tuple(sorted(SCALAR_CURVE_LOGICAL_SUFFIXES)),
    widget_kind="curve",
)

CURVE_LOGICAL_SUFFIXES = frozenset(
    {
        "times",
        "values",
        "inTangentTimes",
        "inTangentValues",
        "inTangentTypes",
        "outTangentTimes",
        "outTangentValues",
        "outTangentTypes",
        "tangentBrokens",
        "preInfinity",
        "postInfinity",
    }
)
CURVE_LOGICAL_GROUP_DEFINITION = LogicalGroupDefinition(
    suffixes=tuple(sorted(CURVE_LOGICAL_SUFFIXES)),
    widget_kind="curve",
)
