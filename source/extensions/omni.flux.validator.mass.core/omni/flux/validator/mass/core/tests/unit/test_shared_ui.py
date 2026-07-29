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

from omni.flux.validator.manager.core import ValidationSchema as _ValidationSchema
from omni.flux.validator.mass.core.schema_tree import shared_ui as _shared_ui
from omni.kit.test import AsyncTestCase
from pydantic import BaseModel, ConfigDict, Field

from .fake_plugins import register_fake_plugins as _register_fake_plugins
from .fake_plugins import unregister_fake_plugins as _unregister_fake_plugins

_SharedIntField = _shared_ui.SharedIntField


class _SharedTextData(BaseModel):
    """Provide an unconstrained string target."""

    shared_value: str = "valid"

    model_config = ConfigDict(validate_assignment=True)


class _LimitedSharedTextData(_SharedTextData):
    """Provide a string target that rejects short values."""

    shared_value: str = Field(default="valid", min_length=3)


def _schema(check_names: tuple[str, ...] = ("FakeCheck", "FakeCheck2")) -> _ValidationSchema:
    """Create a validation schema with the requested fake check plugins."""
    return _ValidationSchema(
        name="Shared UI Test",
        context_plugin={"name": "FakeContext", "data": {}},
        check_plugins=[
            {
                "name": check_name,
                "context_plugin": {"name": "FakeContext", "data": {}},
                "selector_plugins": [{"name": "FakeSelector", "data": {}}],
                "data": {},
            }
            for check_name in check_names
        ],
    )


def _declaration(field_name: str = "shared_int") -> dict:
    """Create a shared integer declaration targeting both fake checks."""
    return {
        "id": "shared_workers",
        "label": "Shared Workers",
        "tooltip": "Applied to both fake checks.",
        "value": 2,
        "targets": [
            {"plugin": "FakeCheck", "field": field_name},
            {"plugin": "FakeCheck2", "field": field_name},
        ],
    }


class TestSharedIntField(AsyncTestCase):
    """Test declarative shared integer bindings."""

    async def setUp(self):
        """Register fake validator plugins."""
        _register_fake_plugins()

    async def tearDown(self):
        """Unregister fake validator plugins."""
        _unregister_fake_plugins()

    async def test_from_schema_with_valid_targets_resolves_both_data_models(self):
        # Arrange
        schema = _schema()

        # Act
        field = _SharedIntField.from_schema(schema, _declaration())

        # Assert
        self.assertEqual(2, len(field.targets))
        self.assertEqual(2, field.value)

    async def test_from_schema_with_target_values_uses_shared_declaration_value(self):
        # Arrange
        schema = _schema()
        schema.check_plugins[0].data.shared_int = 3
        schema.check_plugins[1].data.shared_int = 4

        # Act
        field = _SharedIntField.from_schema(schema, _declaration())

        # Assert
        self.assertEqual(2, field.value)
        self.assertEqual([2, 2], [target.shared_int for target in field.targets])

    async def test_from_schema_with_missing_target_raises_clear_error(self):
        # Arrange
        schema = _schema(("FakeCheck",))

        # Act / Assert
        with self.assertRaisesRegex(ValueError, "FakeCheck2.*not found"):
            _SharedIntField.from_schema(schema, _declaration())

    async def test_from_schema_with_duplicate_target_plugin_raises_clear_error(self):
        # Arrange
        schema = _schema(("FakeCheck", "FakeCheck"))
        declaration = _declaration()
        declaration["targets"] = [{"plugin": "FakeCheck", "field": "shared_int"}]

        # Act / Assert
        with self.assertRaisesRegex(ValueError, "FakeCheck.*more than once"):
            _SharedIntField.from_schema(schema, declaration)

    async def test_from_schema_with_non_integer_target_raises_clear_error(self):
        # Arrange
        schema = _schema()

        # Act / Assert
        with self.assertRaisesRegex(ValueError, "shared_text.*integer"):
            _SharedIntField.from_schema(schema, _declaration("shared_text"))

    async def test_set_value_with_valid_integer_updates_every_target(self):
        # Arrange
        field = _SharedIntField.from_schema(_schema(), _declaration())

        # Act
        accepted = field.set_value(3)

        # Assert
        self.assertTrue(accepted)
        self.assertEqual(3, field.value)
        self.assertEqual([3, 3], [target.shared_int for target in field.targets])

    async def test_set_value_when_later_target_rejects_value_restores_every_target(self):
        # Arrange
        declaration = _declaration()
        declaration["targets"][1]["field"] = "shared_limited_int"
        field = _SharedIntField.from_schema(_schema(), declaration)

        # Act
        accepted = field.set_value(3)

        # Assert
        self.assertFalse(accepted)
        self.assertEqual(2, field.value)
        self.assertEqual(2, field.targets[0].shared_int)
        self.assertEqual(2, field.targets[1].shared_limited_int)

    async def test_shared_value_binding_when_later_text_target_rejects_value_restores_all_targets(self):
        # Arrange
        first_target = _SharedTextData()
        second_target = _LimitedSharedTextData()
        binding = _shared_ui._SharedValueBinding(
            [(first_target, "shared_value"), (second_target, "shared_value")], "valid"
        )

        # Act
        accepted = binding.set_value("x")

        # Assert
        self.assertFalse(accepted)
        self.assertEqual("valid", binding.value)
        self.assertEqual(["valid", "valid"], [target.shared_value for target in binding.targets])
