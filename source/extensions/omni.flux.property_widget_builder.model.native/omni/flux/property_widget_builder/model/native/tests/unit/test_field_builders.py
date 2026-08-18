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

import pathlib

import omni.kit.test
from omni.flux.property_widget_builder.model.native import (
    NATIVE_FIELD_BUILDERS,
    NativeBuilderList,
    NativeChoiceModel,
    NativeDelegate,
    NativeItem,
)
from omni.flux.property_widget_builder.model.native import field_builders as _field_builders
from omni.flux.property_widget_builder.widget import ClaimResult, ItemValueModel


class _Item(NativeItem):
    def __init__(self, value_type: type):
        """Initialize a native property item.

        Args:
            value_type: Exact Python type represented by the item.
        """
        super().__init__()
        self._value_type = value_type

    @property
    def value_type(self) -> type:
        """Return the exact Python type represented by the item.

        Returns:
            Type used by the native field-builder registry.
        """
        return self._value_type


class _ValueModel(ItemValueModel):
    def __init__(self, value):
        """Initialize an editable value model.

        Args:
            value: Initial typed property value.
        """
        super().__init__()
        self._value = value
        self._read_only = False

    def get_value(self):
        """Return the stored value.

        Returns:
            Current typed property value.
        """
        return self._value

    def _set_value(self, value):
        """Store a new value.

        Args:
            value: Typed property value to store.
        """
        self._value = value

    def _on_dirty(self):
        """Handle external invalidation for the in-memory test model."""
        pass

    def refresh(self):
        """Refresh the in-memory test model."""
        pass

    def _get_value_as_string(self) -> str:
        """Return the value as text.

        Returns:
            Text representation of the value.
        """
        return str(self._value)

    def _get_value_as_float(self) -> float:
        """Return the value as a float.

        Returns:
            Floating-point representation of the value.
        """
        return float(self._value)

    def _get_value_as_bool(self) -> bool:
        """Return the value as a Boolean.

        Returns:
            Boolean representation of the value.
        """
        return bool(self._value)

    def _get_value_as_int(self) -> int:
        """Return the value as an integer.

        Returns:
            Integer representation of the value.
        """
        return int(self._value)


class _Model:
    def __init__(self, items):
        """Initialize a property model fixture.

        Args:
            items: Native property items returned by the fixture.
        """
        self._items = items

    def get_all_items(self, include_hidden=True):
        """Return every fixture item.

        Args:
            include_hidden: Accepted for the production model contract.

        Returns:
            Native property items owned by this fixture.
        """
        del include_hidden
        return self._items


class TestNativeFieldBuilders(omni.kit.test.AsyncTestCase):
    async def test_native_choice_selection_writes_typed_value(self):
        """Selecting a native choice writes its original typed value."""
        # Arrange
        value_model = _ValueModel("first")
        choice_model = NativeChoiceModel(value_model, ("first", "second"))

        # Act
        choice_model.get_item_value_model().set_value(1)

        # Assert
        self.assertEqual(value_model.get_value(), "second")
        self.assertEqual(choice_model.get_value(), "second")

    async def test_native_choice_refresh_reads_external_value(self):
        """Refreshing a native choice reads an externally changed value."""
        # Arrange
        value_model = _ValueModel("first")
        choice_model = NativeChoiceModel(value_model, ("first", "second"))
        value_model.set_value("second")

        # Act
        choice_model.refresh()

        # Assert
        self.assertEqual(choice_model.get_item_value_model().as_int, 1)

    async def test_native_read_only_choice_rejects_selection_write_through(self):
        """A read-only choice restores its current selection without mutating the value."""
        # Arrange
        value_model = _ValueModel("first")
        value_model._read_only = True
        choice_model = NativeChoiceModel(value_model, ("first", "second"))

        # Act
        choice_model.get_item_value_model().set_value(1)

        # Assert
        self.assertEqual(value_model.get_value(), "first")
        self.assertEqual(choice_model.get_item_value_model().as_int, 0)

    async def test_register_by_value_type_claims_matching_items(self):
        # Arrange
        builders = NativeBuilderList()
        bool_item = _Item(bool)
        int_item = _Item(int)
        float_item = _Item(float)

        def build(_item):
            return None

        # Act
        returned = builders.register_by_value_type(bool, int)(build)
        result = builders[0].claim_func([bool_item, int_item, float_item])

        # Assert
        self.assertIs(returned, build)
        self.assertIsInstance(result, ClaimResult)
        self.assertEqual(result.primary, [bool_item, int_item])
        self.assertEqual(result.companions, [])
        self.assertIs(builders[0].build_func, build)

    async def test_native_default_builders_return_claim_results(self):
        # Arrange
        item = _Item(pathlib.Path)

        # Act
        results = [builder.claim_func([item]) for builder in NATIVE_FIELD_BUILDERS]

        # Assert
        for result in results:
            self.assertIsInstance(result, ClaimResult)

    async def test_delegate_resolves_native_type_builders_before_fallback(self):
        # Arrange
        bool_item = _Item(bool)
        int_item = _Item(int)
        unknown_item = _Item(dict)
        model = _Model([bool_item, int_item, unknown_item])
        delegate = NativeDelegate()

        # Act
        delegate.resolve_claims(model)

        # Assert
        self.assertIs(delegate.get_widget_builder(bool_item), _field_builders._bool_builder)
        self.assertIs(delegate.get_widget_builder(int_item), _field_builders._integer_builder)
        self.assertIs(delegate.get_widget_builder(unknown_item), _field_builders._fallback_builder)

    async def test_delegate_default_attrs_include_alignment_state(self):
        # Arrange
        delegate = NativeDelegate()

        # Act
        default_attr = delegate.default_attr

        # Assert
        self.assertIn("_right_aligned_labels", default_attr)
        self.assertIs(delegate._get_default_field_builders(), NATIVE_FIELD_BUILDERS)
