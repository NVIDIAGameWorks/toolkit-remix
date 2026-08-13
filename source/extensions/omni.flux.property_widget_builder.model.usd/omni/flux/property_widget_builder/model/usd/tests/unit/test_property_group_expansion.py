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
from omni.flux.property_widget_builder.model.usd import PropertyGroupExpansionMixin


class _ExpansionTarget:
    def __init__(self):
        self.history = []

    def expand_all_groups(self):
        self.history.append("expand")

    def collapse_all_groups(self):
        self.history.append("collapse")


class _DefaultExpansionWrapper(PropertyGroupExpansionMixin):
    def __init__(self, property_widget=None):
        self._property_widget = property_widget


class _CompositeExpansionWrapper(PropertyGroupExpansionMixin):
    def __init__(self, *property_widgets):
        self._property_widgets = property_widgets

    def _iter_property_group_widgets(self):
        return self._property_widgets


class TestPropertyGroupExpansionMixin(omni.kit.test.AsyncTestCase):
    async def test_expand_all_groups_default_property_widget_expands_target(self):
        # Arrange
        target = _ExpansionTarget()
        wrapper = _DefaultExpansionWrapper(target)

        # Act
        wrapper.expand_all_groups()

        # Assert
        self.assertEqual(target.history, ["expand"])

    async def test_collapse_all_groups_default_property_widget_collapses_target(self):
        # Arrange
        target = _ExpansionTarget()
        wrapper = _DefaultExpansionWrapper(target)

        # Act
        wrapper.collapse_all_groups()

        # Assert
        self.assertEqual(target.history, ["collapse"])

    async def test_expand_all_groups_composite_property_widgets_skips_missing_entries(self):
        # Arrange
        target_a = _ExpansionTarget()
        target_b = _ExpansionTarget()
        wrapper = _CompositeExpansionWrapper(target_a, None, target_b)

        # Act
        wrapper.expand_all_groups()

        # Assert
        self.assertEqual(target_a.history, ["expand"])
        self.assertEqual(target_b.history, ["expand"])

    async def test_collapse_all_groups_composite_property_widgets_skips_missing_entries(self):
        # Arrange
        target_a = _ExpansionTarget()
        target_b = _ExpansionTarget()
        wrapper = _CompositeExpansionWrapper(target_a, None, target_b)

        # Act
        wrapper.collapse_all_groups()

        # Assert
        self.assertEqual(target_a.history, ["collapse"])
        self.assertEqual(target_b.history, ["collapse"])

    async def test_expand_all_groups_missing_default_property_widget_is_noop(self):
        # Arrange
        wrapper = _DefaultExpansionWrapper()

        # Act
        wrapper.expand_all_groups()

        # Assert
        self.assertIsNone(wrapper._property_widget)

    async def test_collapse_all_groups_missing_default_property_widget_is_noop(self):
        # Arrange
        wrapper = _DefaultExpansionWrapper()

        # Act
        wrapper.collapse_all_groups()

        # Assert
        self.assertIsNone(wrapper._property_widget)
