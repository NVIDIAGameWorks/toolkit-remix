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

Tests for omni.flux.fcurve.widget.
"""

from .e2e.test_auto_tangents import TestAutoTangents
from .e2e.test_custom_tangents import TestCustomTangents
from .e2e.test_flat_tangents import TestFlatTangents
from .e2e.test_handle_widget import TestHandleWidgetOnly
from .e2e.test_placer_sandbox import TestPlacerSandbox
from .e2e.test_infinity_curves import TestInfinityCurves
from .e2e.test_keyframes import TestKeyframeClamping
from .e2e.test_smooth_tangents import TestSmoothTangents
from .e2e.test_step_tangents import TestStepTangents
from .unit.test_public_api import (
    TestGetSelectionTangentType,
    TestSelectionInfo,
    TestSelectionProperty,
    TestSetSelectedKeysTangentType,
    TestSubscribeCurveChanged,
)
from .unit.test_tangent_linking import (
    TestBoundaryKeyBehavior,
    TestBrokenTangentIndependence,
    TestLinkedMirroring,
    TestMirroringTypePropagation,
)
from .e2e.test_tangent_mirroring import TestTangentMirroringDrag
from .unit.test_tangent_math import (
    TestAutoTangentBoundary,
    TestFlatTangent,
    TestLinearTangent,
)
from .e2e.test_editor import TestEditor

__all__ = [
    "TestAutoTangentBoundary",
    "TestAutoTangents",
    "TestBoundaryKeyBehavior",
    "TestBrokenTangentIndependence",
    "TestCustomTangents",
    "TestEditor",
    "TestFlatTangent",
    "TestFlatTangents",
    "TestGetSelectionTangentType",
    "TestHandleWidgetOnly",
    "TestInfinityCurves",
    "TestKeyframeClamping",
    "TestLinearTangent",
    "TestLinkedMirroring",
    "TestMirroringTypePropagation",
    "TestPlacerSandbox",
    "TestSelectionInfo",
    "TestSelectionProperty",
    "TestSetSelectedKeysTangentType",
    "TestSmoothTangents",
    "TestStepTangents",
    "TestSubscribeCurveChanged",
    "TestTangentMirroringDrag",
]
