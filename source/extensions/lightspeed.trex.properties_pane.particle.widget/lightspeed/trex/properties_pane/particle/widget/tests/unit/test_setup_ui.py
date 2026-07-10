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

from unittest.mock import Mock, patch

import omni.kit.test
from lightspeed.trex.properties_pane.particle.widget.setup_ui import (
    PARTICLE_ATTR_GROUP_FALLBACK,
    PARTICLE_ATTR_GROUP_ORDER,
    ParticleSystemPropertyWidget,
    _add_edit_group_outlets,
    _resolve_curve_logical_group_definition,
    _resolve_edit_group_outlet_group,
)
from lightspeed.trex.properties_pane.particle.widget.particle_edit_groups import (
    PARTICLE_CURVE_LOOKUP,
)
from omni.flux.property_widget_builder.model.usd.logical_group_constants import CURVE_LOGICAL_GROUP_DEFINITION
from pxr import Sdf


_PARTICLE_CURVE_SCHEMA_SUFFIXES = set(CURVE_LOGICAL_GROUP_DEFINITION.suffixes) - {"preInfinity", "postInfinity"}


class _SchemaAttr:
    def __init__(self, display_group: str | None):
        self.GetInfo = Mock(side_effect=lambda key: display_group if key == Sdf.AttributeSpec.DisplayGroupKey else None)


class _SchemaPrim:
    def __init__(self, properties: dict):
        self.properties = properties


class TestParticleSetupUi(omni.kit.test.AsyncTestCase):
    def _assert_curve_definition_error(self, schema_prim, edit_group_layout, message_pattern: str) -> None:
        """Assert invalid curve schema input raises an expected setup error.

        Args:
            schema_prim: Fake generated schema prim to validate.
            edit_group_layout: Particle edit-group layout to resolve.
            message_pattern: Regex expected in the raised ``ValueError``.
        """
        with (
            patch("lightspeed.trex.properties_pane.particle.widget.setup_ui.carb.log_error") as log_error_mock,
            self.assertRaisesRegex(ValueError, message_pattern),
        ):
            _resolve_curve_logical_group_definition(schema_prim, edit_group_layout)
        log_error_mock.assert_not_called()

    async def test_general_group_is_first_particle_group(self):
        self.assertEqual(PARTICLE_ATTR_GROUP_ORDER[0], "General")

    async def test_resolve_edit_group_outlet_group_first_curve_values_group_wins(self):
        # Arrange
        schema_prim = _SchemaPrim(
            {
                "primvars:particle:minSize:x:values": _SchemaAttr("Spawn"),
                "primvars:particle:minSize:y:values": _SchemaAttr("Visual"),
            }
        )
        edit_group_layout = {
            "curve_map": {
                "primvars:particle:minSize:x": "minSize/x",
                "primvars:particle:minSize:y": "minSize/y",
            }
        }

        # Act
        result = _resolve_edit_group_outlet_group(schema_prim, edit_group_layout)

        # Assert
        self.assertEqual(result, "Spawn")

    async def test_resolve_edit_group_outlet_group_empty_first_group_uses_next_curve(self):
        # Arrange
        schema_prim = _SchemaPrim(
            {
                "primvars:particle:minSize:x:values": _SchemaAttr(" "),
                "primvars:particle:minSize:y:values": _SchemaAttr("Visual"),
            }
        )
        edit_group_layout = {
            "curve_map": {
                "primvars:particle:minSize:x": "minSize/x",
                "primvars:particle:minSize:y": "minSize/y",
            }
        }

        # Act
        result = _resolve_edit_group_outlet_group(schema_prim, edit_group_layout)

        # Assert
        self.assertEqual(result, "Visual")

    async def test_resolve_edit_group_outlet_group_no_curve_values_group_uses_fallback(self):
        # Arrange
        schema_prim = _SchemaPrim(
            {
                "primvars:particle:minSize:x:values": _SchemaAttr(None),
                "primvars:particle:minSize:y:values": _SchemaAttr(""),
            }
        )
        edit_group_layout = {
            "curve_map": {
                "primvars:particle:minSize:x": "minSize/x",
                "primvars:particle:minSize:y": "minSize/y",
            }
        }

        # Act
        result = _resolve_edit_group_outlet_group(schema_prim, edit_group_layout)

        # Assert
        self.assertEqual(result, PARTICLE_ATTR_GROUP_FALLBACK)

    async def test_resolve_edit_group_outlet_group_empty_curve_map_returns_none(self):
        # Arrange
        schema_prim = _SchemaPrim({})
        edit_group_layout = {"curve_map": {}}

        # Act
        result = _resolve_edit_group_outlet_group(schema_prim, edit_group_layout)

        # Assert
        self.assertIsNone(result)

    async def test_resolve_edit_group_outlet_group_ignores_unsuffixed_curve_metadata(self):
        # Arrange
        schema_prim = _SchemaPrim(
            {
                "primvars:particle:minSize:x": _SchemaAttr("Ignored"),
                "primvars:particle:minSize:y:values": _SchemaAttr("Visual"),
            }
        )
        edit_group_layout = {
            "curve_map": {
                "primvars:particle:minSize:x": "minSize/x",
                "primvars:particle:minSize:y": "minSize/y",
            }
        }

        # Act
        result = _resolve_edit_group_outlet_group(schema_prim, edit_group_layout)

        # Assert
        self.assertEqual(result, "Visual")

    async def test_resolve_curve_logical_group_definition_requires_full_schema_suffixes(self):
        # Arrange
        curve_ids = ["primvars:particle:minSize:x", "primvars:particle:minSize:y"]
        schema_prim = _SchemaPrim(
            {
                f"{curve_id}:{suffix}": _SchemaAttr(None)
                for curve_id in curve_ids
                for suffix in CURVE_LOGICAL_GROUP_DEFINITION.suffixes
            }
        )
        edit_group_layout = {"curve_map": {curve_id: curve_id for curve_id in curve_ids}}

        # Act
        result = _resolve_curve_logical_group_definition(schema_prim, edit_group_layout)

        # Assert
        self.assertEqual(result, CURVE_LOGICAL_GROUP_DEFINITION)

    async def test_resolve_curve_logical_group_definition_uses_particle_schema_suffixes_without_infinity(self):
        # Arrange
        curve_ids = ["primvars:particle:minSize:x", "primvars:particle:minSize:y"]
        schema_prim = _SchemaPrim(
            {
                f"{curve_id}:{suffix}": _SchemaAttr(None)
                for curve_id in curve_ids
                for suffix in _PARTICLE_CURVE_SCHEMA_SUFFIXES
            }
        )
        edit_group_layout = {"curve_map": {curve_id: curve_id for curve_id in curve_ids}}

        # Act
        result = _resolve_curve_logical_group_definition(schema_prim, edit_group_layout)

        # Assert
        self.assertEqual(set(result.suffixes), _PARTICLE_CURVE_SCHEMA_SUFFIXES)
        self.assertEqual(result.widget_kind, "curve")

    async def test_resolve_curve_logical_group_definition_fails_when_required_attrs_are_missing(self):
        # Arrange
        schema_prim = _SchemaPrim({"primvars:particle:minSize:x:times": _SchemaAttr(None)})
        edit_group_layout = {"curve_map": {"primvars:particle:minSize:x": "minSize/x"}}

        # Act/Assert
        self._assert_curve_definition_error(schema_prim, edit_group_layout, "missing required curve schema attrs")

    async def test_resolve_curve_logical_group_definition_fails_when_tangent_attrs_are_missing(self):
        # Arrange
        curve_id = "primvars:particle:minSize:x"
        schema_suffixes = _PARTICLE_CURVE_SCHEMA_SUFFIXES - {"inTangentTimes"}
        schema_prim = _SchemaPrim({f"{curve_id}:{suffix}": _SchemaAttr(None) for suffix in schema_suffixes})
        edit_group_layout = {"curve_map": {curve_id: "minSize/x"}}

        # Act/Assert
        self._assert_curve_definition_error(schema_prim, edit_group_layout, "missing required curve schema attrs")

    async def test_resolve_curve_logical_group_definition_fails_when_only_scalar_attrs_exist(self):
        # Arrange
        curve_id = "primvars:particle:minSize:x"
        schema_prim = _SchemaPrim(
            {
                f"{curve_id}:times": _SchemaAttr(None),
                f"{curve_id}:values": _SchemaAttr(None),
            }
        )
        edit_group_layout = {"curve_map": {curve_id: "minSize/x"}}

        # Act/Assert
        self._assert_curve_definition_error(schema_prim, edit_group_layout, "missing required curve schema attrs")

    async def test_resolve_curve_logical_group_definition_fails_when_curve_map_is_empty(self):
        # Arrange
        schema_prim = _SchemaPrim({})
        edit_group_layout = {"curve_map": {}}

        # Act/Assert
        self._assert_curve_definition_error(schema_prim, edit_group_layout, "curve_map")

    async def test_add_edit_group_outlets_skips_invalid_curve_outlet_schema(self):
        # Arrange
        group_items = {}
        schema_prim = _SchemaPrim({"primvars:particle:minSize:x:values": _SchemaAttr("Visual")})
        edit_groups = {
            "invalid_size": {
                "curve_map": {"primvars:particle:minSize:x": "minSize/x"},
                "display_name": "Particle Size",
            }
        }
        pre_open_callback_builder = Mock()

        with patch("lightspeed.trex.properties_pane.particle.widget.setup_ui.carb.log_error") as log_error_mock:
            # Act
            _add_edit_group_outlets(
                group_items=group_items,
                schema_prim=schema_prim,
                edit_groups=edit_groups.values(),
                context_name="TestContext",
                target_paths=["/Particle"],
                pre_open_callback_builder=pre_open_callback_builder,
            )

        # Assert
        self.assertEqual(group_items, {})
        log_error_mock.assert_called_once()
        self.assertIn("missing required curve schema attrs", log_error_mock.call_args.args[0])
        pre_open_callback_builder.assert_not_called()

    async def test_particle_curve_lookup_tracks_raw_curve_control_rows_only(self):
        for attr_name in PARTICLE_CURVE_LOOKUP:
            with self.subTest(attr_name=attr_name):
                self.assertTrue(attr_name.startswith("primvars:particle"))
                self.assertNotIn(":values", attr_name)
                self.assertNotIn(":times", attr_name)

    async def test_particle_curve_lookup_excludes_curve_storage_attrs(self):
        for attr_name in PARTICLE_CURVE_LOOKUP:
            for suffix in (
                ":values",
                ":times",
                ":inTangentValues",
                ":outTangentValues",
                ":preInfinity",
                ":postInfinity",
            ):
                with self.subTest(attr_name=attr_name, suffix=suffix):
                    self.assertNotIn(f"{attr_name}{suffix}", PARTICLE_CURVE_LOOKUP)

    async def test_particle_curve_lookup_excludes_non_curve_particle_attrs(self):
        self.assertNotIn("primvars:particle:applyGravity", PARTICLE_CURVE_LOOKUP)

    async def test_extract_curve_id_handles_curve_editor_infinity_attrs(self):
        self.assertEqual(
            ParticleSystemPropertyWidget._extract_curve_id("primvars:particle:minRotationSpeed:preInfinity"),
            "primvars:particle:minRotationSpeed",
        )
        self.assertEqual(
            ParticleSystemPropertyWidget._extract_curve_id("primvars:particle:minRotationSpeed:postInfinity"),
            "primvars:particle:minRotationSpeed",
        )

    async def test_extract_curve_id_ignores_unsuffixed_curve_controller_attrs(self):
        self.assertIsNone(ParticleSystemPropertyWidget._extract_curve_id("primvars:particle:minRotationSpeed"))

    async def test_pre_open_callback_seeds_single_attr_before_opening_editor(self):
        # Arrange
        widget = ParticleSystemPropertyWidget.__new__(ParticleSystemPropertyWidget)
        widget._context_name = "TestContext"
        widget._property_model = Mock()
        open_editor = Mock()

        with patch(
            "lightspeed.trex.properties_pane.particle.widget.setup_ui._seed_current_animated_attrs_from_legacy",
            return_value=True,
        ) as seed_current:
            callback = widget._build_pre_open_callback("primvars:particle:minSize:x", ["/Particle"])

            # Act
            callback(open_editor)

        # Assert
        seed_current.assert_called_once_with("primvars:particle:minSize:x", "TestContext", ["/Particle"])
        widget._property_model.refresh.assert_called_once_with()
        open_editor.assert_called_once_with()

    async def test_pre_open_callback_seeds_attr_list_in_order_before_opening_editor(self):
        # Arrange
        widget = ParticleSystemPropertyWidget.__new__(ParticleSystemPropertyWidget)
        widget._context_name = "TestContext"
        widget._property_model = Mock()
        open_editor = Mock()
        animated_attr_names = ["primvars:particle:minSize:x", "primvars:particle:minSize:y"]
        target_paths = ["/ParticleA", "/ParticleB"]

        with patch(
            "lightspeed.trex.properties_pane.particle.widget.setup_ui._seed_current_animated_attrs_from_legacy",
            return_value=True,
        ) as seed_current:
            callback = widget._build_pre_open_callback(animated_attr_names, target_paths)

            # Act
            callback(open_editor)

        # Assert
        seed_current.assert_called_once_with(animated_attr_names, "TestContext", target_paths)
        widget._property_model.refresh.assert_called_once_with()
        open_editor.assert_called_once_with()

    async def test_pre_open_callback_without_seed_only_opens_editor(self):
        # Arrange
        widget = ParticleSystemPropertyWidget.__new__(ParticleSystemPropertyWidget)
        widget._context_name = "TestContext"
        widget._property_model = Mock()
        open_editor = Mock()

        with patch(
            "lightspeed.trex.properties_pane.particle.widget.setup_ui._seed_current_animated_attrs_from_legacy",
            return_value=False,
        ) as seed_current:
            callback = widget._build_pre_open_callback("primvars:particle:minSize:x", ["/Particle"])

            # Act
            callback(open_editor)

        # Assert
        seed_current.assert_called_once_with("primvars:particle:minSize:x", "TestContext", ["/Particle"])
        widget._property_model.refresh.assert_not_called()
        open_editor.assert_called_once_with()
