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

from types import SimpleNamespace

import omni.kit.test
from omni.flux.properties_pane.materials.usd.widget.material_visibility_orchestrator import (
    MaterialVisibilityOrchestrator,
)


def _make_placeholder(name=None, condition=None):
    """Build a SimpleNamespace placeholder mimicking the MDL placeholder API."""
    return SimpleNamespace(GetName=lambda: name, GetEnableIfCondition=lambda: condition)


def _make_entry(attr_id=None, condition=None, metadata_source=None):
    """Build a minimal material visibility entry for direct helper method tests."""
    return SimpleNamespace(attr_id=attr_id, condition=condition, metadata_source=metadata_source)


def _make_value_item(value):
    """Build a minimal rendered item exposing a single value model."""
    return SimpleNamespace(
        value_models=[SimpleNamespace(get_value=lambda: value, subscribe_value_changed_fn=lambda _: None)]
    )


def _make_adapter(*entries, items=None):
    """Build a material orchestrator using the explicit bind-per-attribute API."""
    adapter = MaterialVisibilityOrchestrator()
    items = items or {}
    for entry in entries:
        adapter.bind_attribute(
            attr_id=entry.attr_id,
            condition=entry.condition,
            metadata_source=entry.metadata_source,
            item_or_items=items.get(entry.attr_id),
        )
    return adapter


class TestMaterialVisibilityOrchestrator(omni.kit.test.AsyncTestCase):
    """Unit tests for the material-specific MaterialVisibilityOrchestrator."""

    async def test_can_bind_attribute_returns_true_for_inputs_prefix(self):
        # Arrange
        attr_id = "inputs:enable_normal"
        adapter = MaterialVisibilityOrchestrator()

        # Act
        result = adapter.can_bind_attribute(attr_id)

        # Assert
        self.assertTrue(result)

    async def test_can_bind_attribute_returns_true_for_raw_name(self):
        # Arrange
        attr_id = "enable_normal"
        adapter = MaterialVisibilityOrchestrator()

        # Act
        result = adapter.can_bind_attribute(attr_id)

        # Assert
        self.assertTrue(result)

    async def test_can_bind_attribute_returns_false_for_outputs_prefix(self):
        # Arrange
        attr_id = "outputs:result"
        adapter = MaterialVisibilityOrchestrator()

        # Act
        result = adapter.can_bind_attribute(attr_id)

        # Assert
        self.assertFalse(result)

    async def test_can_bind_attribute_returns_false_for_empty_value(self):
        # Arrange
        attr_id = None
        adapter = MaterialVisibilityOrchestrator()

        # Act
        result = adapter.can_bind_attribute(attr_id)

        # Assert
        self.assertFalse(result)

    async def test_can_bind_attribute_returns_false_for_empty_string(self):
        # Arrange
        attr_id = ""
        adapter = MaterialVisibilityOrchestrator()

        # Act
        result = adapter.can_bind_attribute(attr_id)

        # Assert
        self.assertFalse(result)

    async def test_get_attr_id_uses_placeholder_get_name_with_inputs_prefix(self):
        # Arrange
        placeholder = _make_placeholder(name="inputs:foo")
        entry = _make_entry(attr_id="ignored", metadata_source=placeholder)
        adapter = MaterialVisibilityOrchestrator()

        # Act
        result = adapter._get_attr_id(entry)

        # Assert
        self.assertEqual(result, "foo")

    async def test_get_attr_id_uses_placeholder_get_name_for_raw_name(self):
        # Arrange
        placeholder = _make_placeholder(name="bar")
        entry = _make_entry(attr_id="ignored", metadata_source=placeholder)
        adapter = MaterialVisibilityOrchestrator()

        # Act
        result = adapter._get_attr_id(entry)

        # Assert
        self.assertEqual(result, "bar")

    async def test_get_attr_id_falls_back_to_attr_id_when_placeholder_missing(self):
        # Arrange
        entry = _make_entry(attr_id="bar")
        adapter = MaterialVisibilityOrchestrator()

        # Act
        result = adapter._get_attr_id(entry)

        # Assert
        self.assertEqual(result, "bar")

    async def test_get_attr_id_returns_none_for_outputs_placeholder(self):
        # Arrange
        placeholder = _make_placeholder(name="outputs:result")
        entry = _make_entry(attr_id="inputs:ignored", metadata_source=placeholder)
        adapter = MaterialVisibilityOrchestrator()

        # Act
        result = adapter._get_attr_id(entry)

        # Assert
        self.assertIsNone(result)

    async def test_get_enable_if_condition_uses_placeholder_method_as_canonical_source(self):
        # Arrange
        placeholder = _make_placeholder(name="inputs:driver", condition="inputs:driver == True")
        entry = _make_entry(attr_id="inputs:driver", metadata_source=placeholder, condition="ignored fallback")
        adapter = MaterialVisibilityOrchestrator()

        # Act
        result = adapter._get_enable_if_condition(entry)

        # Assert
        self.assertEqual(result, "inputs:driver == True")

    async def test_get_enable_if_condition_falls_back_to_super_when_placeholder_missing(self):
        # Arrange
        entry = _make_entry(attr_id="affected", condition="driver == True")
        adapter = MaterialVisibilityOrchestrator()

        # Act
        result = adapter._get_enable_if_condition(entry)

        # Assert
        self.assertEqual(result, "driver == True")

    async def test_bind_attribute_groups_raw_and_prefixed_drivers_under_same_normalized_id(self):
        # Arrange
        driver_placeholder = _make_placeholder(name="driver", condition=None)
        affected_placeholder = _make_placeholder(name="inputs:affected", condition="driver == True")
        driver = _make_entry(attr_id="driver", metadata_source=driver_placeholder)
        affected = _make_entry(attr_id="inputs:affected", metadata_source=affected_placeholder)
        affected_item = SimpleNamespace(hidden=False)

        # Act
        adapter = _make_adapter(
            driver, affected, items={"driver": _make_value_item(False), "inputs:affected": affected_item}
        )
        adapter.sync_and_evaluate_bindings()

        # Assert
        self.assertTrue(affected_item.hidden)

    async def test_bind_attribute_uses_placeholder_get_enable_if_condition_over_entry_condition(self):
        # Arrange
        driver = _make_entry(
            attr_id="inputs:driver",
            metadata_source=_make_placeholder(name="inputs:driver", condition=None),
        )
        affected = _make_entry(
            attr_id="inputs:affected",
            metadata_source=_make_placeholder(name="inputs:affected", condition="driver == True"),
            condition="missing == False",
        )
        affected_item = SimpleNamespace(hidden=False)

        # Act
        adapter = _make_adapter(
            driver,
            affected,
            items={"inputs:driver": _make_value_item(True), "inputs:affected": affected_item},
        )

        # Assert
        adapter.sync_and_evaluate_bindings()
        self.assertFalse(affected_item.hidden)

    async def test_bind_attribute_uses_material_placeholder_metadata(self):
        # Arrange
        driver_placeholder = _make_placeholder(name="inputs:driver", condition=None)
        affected_placeholder = _make_placeholder(name="inputs:affected", condition="driver == True")
        driver_item = _make_value_item(False)
        affected_item = SimpleNamespace(hidden=False)
        adapter = MaterialVisibilityOrchestrator()

        # Act
        adapter.bind_attribute(
            attr_id="inputs:driver",
            metadata_source=driver_placeholder,
            item_or_items=driver_item,
        )
        adapter.bind_attribute(
            attr_id="inputs:affected",
            metadata_source=affected_placeholder,
            item_or_items=affected_item,
        )
        adapter.sync_and_evaluate_bindings()

        # Assert
        self.assertTrue(affected_item.hidden)
