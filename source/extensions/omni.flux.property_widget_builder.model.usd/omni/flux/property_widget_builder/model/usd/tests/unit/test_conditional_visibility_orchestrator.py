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
from unittest.mock import Mock, patch

import omni.kit.test
from omni.flux.property_widget_builder.model.usd.conditional_visibility_orchestrator import (
    ConditionalVisibilityOrchestrator,
)


def _make_value_model(initial_value):
    """Build a minimal mock value model with get/set semantics matching omni.ui."""
    state = {"value": initial_value}
    return SimpleNamespace(
        get_value=lambda: state["value"],
        set_value=lambda new_value: state.update({"value": new_value}),
        subscribe_value_changed_fn=Mock(return_value=Mock()),
    )


def _make_subscribable_value_model(initial_value):
    return _make_value_model(initial_value)


def _make_item_with_value_model(value_model):
    return SimpleNamespace(value_models=[value_model])


def _make_item_with_value_models(value_models):
    return SimpleNamespace(value_models=list(value_models))


def _make_visibility_item():
    return SimpleNamespace(hidden=False)


def _make_entry(attr_id, condition=None, metadata_source=None):
    return SimpleNamespace(attr_id=attr_id, condition=condition, metadata_source=metadata_source)


def _make_adapter(*entries, items=None):
    """Build an orchestrator using the explicit bind-per-attribute API."""
    adapter = ConditionalVisibilityOrchestrator()
    items = items or {}
    for entry in entries:
        adapter.bind_attribute(
            attr_id=entry.attr_id,
            condition=entry.condition,
            metadata_source=entry.metadata_source,
            item_or_items=items.get(entry.attr_id),
        )
    return adapter


class TestConditionalVisibilityOrchestrator(omni.kit.test.AsyncTestCase):
    """Unit tests for the shared ConditionalVisibilityOrchestrator condition lifecycle manager."""

    async def test_can_bind_attribute_returns_true_for_attr_id(self):
        # Arrange
        adapter = ConditionalVisibilityOrchestrator()

        # Act
        result = adapter.can_bind_attribute("driver")

        # Assert
        self.assertTrue(result)

    async def test_can_bind_attribute_returns_false_for_empty_attr_id(self):
        # Arrange
        adapter = ConditionalVisibilityOrchestrator()

        # Act
        result = adapter.can_bind_attribute("")

        # Assert
        self.assertFalse(result)

    async def test_init_with_missing_driver_yields_no_bindings(self):
        # Arrange
        affected = _make_entry(attr_id="affected", condition="missing == True")

        # Act
        adapter = _make_adapter(affected)
        adapter.sync_and_evaluate_bindings()

        # Assert
        self.assertEqual(adapter._condition_bindings, ())

    async def test_init_with_unsupported_syntax_yields_no_bindings(self):
        # Arrange
        affected = _make_entry(attr_id="affected", condition="not(parseable")

        # Act
        adapter = _make_adapter(affected)
        adapter.sync_and_evaluate_bindings()

        # Assert
        self.assertEqual(adapter._condition_bindings, ())

    async def test_evaluate_bindings_updates_hidden_state_when_condition_false(self):
        # Arrange
        driver = _make_entry(attr_id="driver")
        affected = _make_entry(attr_id="affected", condition="driver == True")
        affected_item = _make_visibility_item()
        adapter = _make_adapter(
            driver,
            affected,
            items={"driver": _make_item_with_value_model(_make_value_model(False)), "affected": affected_item},
        )

        # Act
        adapter.sync_and_evaluate_bindings()

        # Assert
        self.assertTrue(affected_item.hidden)

    async def test_evaluate_bindings_updates_hidden_state_when_condition_true(self):
        # Arrange
        driver = _make_entry(attr_id="driver")
        affected = _make_entry(attr_id="affected", condition="driver == True")
        affected_item = _make_visibility_item()
        adapter = _make_adapter(
            driver,
            affected,
            items={"driver": _make_item_with_value_model(_make_value_model(True)), "affected": affected_item},
        )

        # Act
        adapter.sync_and_evaluate_bindings()

        # Assert
        self.assertFalse(affected_item.hidden)

    async def test_evaluate_bindings_updates_hidden_state_for_changed_driver(self):
        # Arrange
        driver = _make_entry(attr_id="driver")
        affected = _make_entry(attr_id="affected", condition="driver == True")
        value_model = _make_value_model(True)
        affected_item = _make_visibility_item()
        adapter = _make_adapter(
            driver, affected, items={"driver": _make_item_with_value_model(value_model), "affected": affected_item}
        )
        adapter.sync_and_evaluate_bindings()
        value_model.set_value(False)

        # Act
        adapter._evaluate_bindings(changed_driver_attr_id="driver")

        # Assert
        self.assertTrue(affected_item.hidden)

    async def test_evaluate_bindings_applies_visibility_to_bound_affected_items(self):
        # Arrange
        driver = _make_entry(attr_id="driver")
        affected = _make_entry(attr_id="affected", condition="driver == True")
        value_model = _make_value_model(True)
        affected_item = _make_visibility_item()
        adapter = _make_adapter(
            driver,
            affected,
            items={"driver": _make_item_with_value_model(value_model), "affected": affected_item},
        )
        adapter.sync_and_evaluate_bindings()
        value_model.set_value(False)

        # Act
        adapter._evaluate_bindings(changed_driver_attr_id="driver")

        # Assert
        self.assertTrue(affected_item.hidden)

        # Act
        value_model.set_value(True)
        adapter._evaluate_bindings(changed_driver_attr_id="driver")

        # Assert
        self.assertFalse(affected_item.hidden)

    async def test_evaluate_bindings_applies_visibility_to_multiple_bound_affected_items(self):
        # Arrange
        driver = _make_entry(attr_id="driver")
        affected = _make_entry(attr_id="affected", condition="driver == True")
        value_model = _make_value_model(True)
        affected_item = _make_visibility_item()
        related_item = _make_visibility_item()
        adapter = _make_adapter(
            driver,
            affected,
            items={
                "driver": _make_item_with_value_model(value_model),
                "affected": (affected_item, related_item),
            },
        )
        adapter.sync_and_evaluate_bindings()
        value_model.set_value(False)

        # Act
        adapter._evaluate_bindings(changed_driver_attr_id="driver")

        # Assert
        self.assertTrue(affected_item.hidden)
        self.assertTrue(related_item.hidden)

    async def test_evaluate_bindings_updates_hidden_state_for_all_bindings(self):
        # Arrange
        driver = _make_entry(attr_id="driver")
        affected_a = _make_entry(attr_id="a", condition="driver == True")
        affected_b = _make_entry(attr_id="b", condition="driver == False")
        affected_a_item = _make_visibility_item()
        affected_b_item = _make_visibility_item()
        adapter = _make_adapter(
            driver,
            affected_a,
            affected_b,
            items={
                "driver": _make_item_with_value_model(_make_value_model(False)),
                "a": affected_a_item,
                "b": affected_b_item,
            },
        )

        # Act
        adapter.sync_and_evaluate_bindings()

        # Assert
        self.assertTrue(affected_a_item.hidden)
        self.assertFalse(affected_b_item.hidden)

    async def test_del_clears_subscriptions_and_marks_inactive(self):
        # Arrange
        driver = _make_entry(attr_id="driver")
        affected = _make_entry(attr_id="affected", condition="driver == True")
        adapter = _make_adapter(
            driver,
            affected,
            items={"driver": _make_item_with_value_model(_make_subscribable_value_model(True))},
        )
        adapter.sync_and_evaluate_bindings()
        self.assertTrue(adapter._value_model_subscriptions)

        # Act
        adapter.__del__()

        # Assert
        self.assertFalse(adapter._active)
        self.assertEqual(adapter._value_model_subscriptions, [])

    async def test_get_driver_value_uses_first_value_model_when_item_exposes_collection(self):
        # Arrange
        driver = _make_entry(attr_id="driver")
        affected = _make_entry(attr_id="affected", condition="driver == True")
        affected_item = _make_visibility_item()
        adapter = _make_adapter(
            driver,
            affected,
            items={"driver": _make_item_with_value_models([_make_value_model(False)]), "affected": affected_item},
        )

        # Act
        adapter.sync_and_evaluate_bindings()

        # Assert
        self.assertTrue(affected_item.hidden)

    async def test_driver_value_subscription_schedules_known_driver(self):
        # Arrange
        driver = _make_entry(attr_id="driver")
        affected = _make_entry(attr_id="affected", condition="driver == True")
        value_model = _make_subscribable_value_model(True)
        adapter = _make_adapter(driver, affected, items={"driver": _make_item_with_value_model(value_model)})
        adapter.sync_and_evaluate_bindings()
        on_driver_value_changed = value_model.subscribe_value_changed_fn.call_args.args[0]
        value_model.set_value(False)

        # Act
        with patch.object(adapter, "_schedule_evaluate_bindings") as schedule_evaluate_bindings_mock:
            on_driver_value_changed(value_model)

        # Assert
        schedule_evaluate_bindings_mock.assert_called_once_with("driver")

    async def test_non_driver_value_model_is_not_subscribed(self):
        # Arrange
        driver = _make_entry(attr_id="driver")
        affected = _make_entry(attr_id="affected", condition="driver == True")
        driver_value_model = _make_value_model(True)
        affected_value_model = _make_subscribable_value_model("affected")
        adapter = _make_adapter(
            driver,
            affected,
            items={
                "driver": _make_item_with_value_model(driver_value_model),
                "affected": _make_item_with_value_model(affected_value_model),
            },
        )

        # Act
        adapter.sync_and_evaluate_bindings()

        # Assert
        affected_value_model.subscribe_value_changed_fn.assert_not_called()

    async def test_driver_value_subscription_ignores_value_model_when_inactive(self):
        # Arrange
        driver = _make_entry(attr_id="driver")
        affected = _make_entry(attr_id="affected", condition="driver == True")
        value_model = _make_subscribable_value_model(True)
        affected_item = _make_visibility_item()
        adapter = _make_adapter(
            driver, affected, items={"driver": _make_item_with_value_model(value_model), "affected": affected_item}
        )
        adapter.sync_and_evaluate_bindings()
        adapter._active = False
        on_driver_value_changed = value_model.subscribe_value_changed_fn.call_args.args[0]
        value_model.set_value(False)

        # Act
        on_driver_value_changed(value_model)

        # Assert
        self.assertFalse(affected_item.hidden)

    async def test_evaluate_skips_binding_when_evaluation_raises(self):
        # Arrange
        driver = _make_entry(attr_id="driver")
        affected = _make_entry(attr_id="affected", condition="driver == True")
        affected_item = _make_visibility_item()
        adapter = _make_adapter(
            driver,
            affected,
            items={
                "driver": _make_item_with_value_model(_make_value_model("not_boolean_friendly")),
                "affected": affected_item,
            },
        )

        # Act
        adapter.sync_and_evaluate_bindings()

        # Assert
        self.assertFalse(affected_item.hidden)
