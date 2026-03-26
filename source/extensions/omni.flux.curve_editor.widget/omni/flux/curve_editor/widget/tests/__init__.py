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

Curve Editor Tests.
"""

from .e2e.test_integration import (
    TestUndoRedo,
    TestMultiCurveEditing,
    TestDataFlow,
    TestTangentTypes,
    TestInfinityTypes,
)
from .e2e.test_toolbar import TestToolbar
from .e2e.test_primvar_integration import TestPrimvarIntegration
from .e2e.test_fcurve_only import TestFCurveOnly

__all__ = [
    "TestDataFlow",
    "TestFCurveOnly",
    "TestInfinityTypes",
    "TestMultiCurveEditing",
    "TestPrimvarIntegration",
    "TestTangentTypes",
    "TestToolbar",
    "TestUndoRedo",
]
