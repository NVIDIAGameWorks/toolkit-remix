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

__all__ = ["TestLightGizmosModel"]

from unittest.mock import MagicMock

from omni.kit.test import AsyncTestCase

from lightspeed.light.gizmos.model import LightGizmosModel


class TestLightGizmosModel(AsyncTestCase):
    """REMIX-3969: tests for light gizmo model visibility helpers."""

    async def test_parent_resolves_in_composition_returns_true_when_prim_has_no_parent(self):
        """Falsy parent short-circuits to True."""
        # Arrange
        prim = MagicMock()
        prim.GetParent.return_value = None

        # Act
        result = LightGizmosModel._parent_resolves_in_composition(prim)

        # Assert
        self.assertTrue(result)

    async def test_parent_resolves_in_composition_returns_true_when_parent_is_pseudo_root(self):
        """Pseudo-root parent short-circuits to True without consulting HasDefiningSpecifier."""
        # Arrange
        parent = MagicMock()
        parent.IsPseudoRoot.return_value = True
        prim = MagicMock()
        prim.GetParent.return_value = parent

        # Act
        result = LightGizmosModel._parent_resolves_in_composition(prim)

        # Assert
        self.assertTrue(result)
        parent.HasDefiningSpecifier.assert_not_called()

    async def test_parent_resolves_in_composition_returns_true_when_parent_has_defining_specifier(self):
        """Parent with a `def` or `class` opinion in any layer returns True."""
        # Arrange
        parent = MagicMock()
        parent.IsPseudoRoot.return_value = False
        parent.HasDefiningSpecifier.return_value = True
        prim = MagicMock()
        prim.GetParent.return_value = parent

        # Act
        result = LightGizmosModel._parent_resolves_in_composition(prim)

        # Assert
        self.assertTrue(result)

    async def test_parent_resolves_in_composition_returns_false_when_parent_only_has_over_opinions(self):
        """Parent with only `over` opinions (no def/class) returns False (REMIX-3969 bug case)."""
        # Arrange
        parent = MagicMock()
        parent.IsPseudoRoot.return_value = False
        parent.HasDefiningSpecifier.return_value = False
        prim = MagicMock()
        prim.GetParent.return_value = parent

        # Act
        result = LightGizmosModel._parent_resolves_in_composition(prim)

        # Assert
        self.assertFalse(result)
