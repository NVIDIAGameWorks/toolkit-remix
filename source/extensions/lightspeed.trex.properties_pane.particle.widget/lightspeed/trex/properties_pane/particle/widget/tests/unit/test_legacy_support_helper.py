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
from lightspeed.trex.properties_pane.particle.widget.legacy_support_helper import (
    animated_attr_has_usable_keys,
    seed_current_animated_attr_from_legacy,
)
from lightspeed.trex.properties_pane.particle.widget.particle_edit_groups import PARTICLE_LEGACY_ANIMATION_MAPPINGS
from pxr import Gf, Sdf, Usd
from unittest.mock import patch


class _SchemaAttr:
    def __init__(self, default):
        self.default = default


class _Context:
    def __init__(self, stage):
        self._stage = stage

    def get_stage(self):
        return self._stage


class TestLegacySupportHelper(omni.kit.test.AsyncTestCase):
    async def setUp(self):  # pyright: ignore[reportIncompatibleMethodOverride]
        self._stages = []

    async def tearDown(self):  # pyright: ignore[reportIncompatibleMethodOverride]
        self._stages = []

    def _create_prim(self):
        stage = Usd.Stage.CreateInMemory()
        self._stages.append(stage)
        return stage.DefinePrim("/Particle", "Mesh")

    def _create_float_array_attr(self, prim, attr_name, value):
        attr = prim.CreateAttribute(attr_name, Sdf.ValueTypeNames.FloatArray)
        attr.Set(value)
        return attr

    async def test_mapping_lookup_returns_curve_mapping(self):
        # Arrange
        attr_name = "primvars:particle:minSpawnSize"

        # Act
        mapping = PARTICLE_LEGACY_ANIMATION_MAPPINGS.get(attr_name)

        # Assert
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping["kind"], "curve")
        self.assertEqual(mapping["animated"][0], "primvars:particle:minSize:x")
        self.assertEqual(mapping["animated"][1], "primvars:particle:minSize:y")

    async def test_mapping_lookup_returns_gradient_mapping(self):
        # Arrange
        attr_name = "primvars:particle:minSpawnColor"

        # Act
        mapping = PARTICLE_LEGACY_ANIMATION_MAPPINGS.get(attr_name)

        # Assert
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping["kind"], "gradient")
        self.assertEqual(mapping["animated"][0], "primvars:particle:minColor")

    async def test_animated_attr_has_usable_keys_rejects_empty_and_mismatched_arrays(self):
        # Arrange
        empty_prim = self._create_prim()
        self._create_float_array_attr(empty_prim, "primvars:particle:emptySize:times", [])
        self._create_float_array_attr(empty_prim, "primvars:particle:emptySize:values", [])
        mismatched_prim = self._create_prim()
        self._create_float_array_attr(mismatched_prim, "primvars:particle:mismatchedSize:times", [0.0, 1.0])
        self._create_float_array_attr(mismatched_prim, "primvars:particle:mismatchedSize:values", [10.0])

        # Act
        empty_result = animated_attr_has_usable_keys(empty_prim, "primvars:particle:emptySize", "curve")
        mismatched_result = animated_attr_has_usable_keys(mismatched_prim, "primvars:particle:mismatchedSize", "curve")

        # Assert
        self.assertFalse(empty_result)
        self.assertFalse(mismatched_result)

    async def test_animated_attr_has_usable_keys_accepts_matching_arrays(self):
        # Arrange
        prim = self._create_prim()
        self._create_float_array_attr(prim, "primvars:particle:minSize:x:times", [0.0, 1.0])
        self._create_float_array_attr(prim, "primvars:particle:minSize:x:values", [10.0, 20.0])

        # Act
        result = animated_attr_has_usable_keys(prim, "primvars:particle:minSize:x", "curve")

        # Assert
        self.assertTrue(result)

    async def test_mapped_legacy_attrs_are_hidden_unconditionally(self):
        # Assert
        self.assertIn("primvars:particle:minSpawnSize", PARTICLE_LEGACY_ANIMATION_MAPPINGS)
        self.assertIn("primvars:particle:maxTargetColor", PARTICLE_LEGACY_ANIMATION_MAPPINGS)
        self.assertNotIn("primvars:particle:minSize:x", PARTICLE_LEGACY_ANIMATION_MAPPINGS)

    async def test_existing_animated_keys_are_not_overwritten(self):
        # Arrange
        prim = self._create_prim()
        legacy_attr = prim.CreateAttribute("primvars:particle:minSpawnRotationSpeed", Sdf.ValueTypeNames.Float)
        legacy_attr.Set(5.0)
        self._create_float_array_attr(prim, "primvars:particle:minRotationSpeed:times", [0.0, 1.0])
        self._create_float_array_attr(prim, "primvars:particle:minRotationSpeed:values", [5.0, 9.0])
        schema_prim = type(
            "_SchemaPrim",
            (),
            {"properties": {"primvars:particle:minSpawnRotationSpeed": _SchemaAttr(0.0)}},
        )()

        # Act
        with (
            patch(
                "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.omni.usd.get_context",
                return_value=_Context(prim.GetStage()),
            ),
            patch(
                "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.get_schema_prim",
                return_value=(None, schema_prim),
            ),
        ):
            result = seed_current_animated_attr_from_legacy(
                "primvars:particle:minRotationSpeed", "", str(prim.GetPath())
            )

        # Assert
        self.assertFalse(result)

    async def test_default_legacy_values_do_not_seed_animated_attr(self):
        # Arrange
        prim = self._create_prim()
        spawn_attr = prim.CreateAttribute("primvars:particle:minSpawnSize", Sdf.ValueTypeNames.Float2)
        target_attr = prim.CreateAttribute("primvars:particle:minTargetSize", Sdf.ValueTypeNames.Float2)
        spawn_attr.Set(Gf.Vec2f(10.0, 10.0))
        target_attr.Set(Gf.Vec2f(0.0, 0.0))
        schema_prim = type(
            "_SchemaPrim",
            (),
            {
                "properties": {
                    "primvars:particle:minSpawnSize": _SchemaAttr(Gf.Vec2f(10.0, 10.0)),
                    "primvars:particle:minTargetSize": _SchemaAttr(Gf.Vec2f(0.0, 0.0)),
                }
            },
        )()

        # Act
        with patch(
            "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.omni.kit.commands.execute"
        ) as execute:
            with (
                patch(
                    "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.omni.usd.get_context",
                    return_value=_Context(prim.GetStage()),
                ),
                patch(
                    "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.get_schema_prim",
                    return_value=(None, schema_prim),
                ),
            ):
                result = seed_current_animated_attr_from_legacy("primvars:particle:minSize:x", "", str(prim.GetPath()))

        # Assert
        self.assertFalse(result)
        execute.assert_not_called()

    async def test_seed_curve_from_legacy_uses_start_and_end_values(self):
        # Arrange
        prim = self._create_prim()
        spawn_attr = prim.CreateAttribute("primvars:particle:minSpawnSize", Sdf.ValueTypeNames.Float2)
        target_attr = prim.CreateAttribute("primvars:particle:minTargetSize", Sdf.ValueTypeNames.Float2)
        spawn_attr.Set(Gf.Vec2f(25.0, 10.0))
        target_attr.Set(Gf.Vec2f(50.0, 20.0))
        schema_prim = type(
            "_SchemaPrim",
            (),
            {
                "properties": {
                    "primvars:particle:minSpawnSize": _SchemaAttr(Gf.Vec2f(10.0, 10.0)),
                    "primvars:particle:minTargetSize": _SchemaAttr(Gf.Vec2f(0.0, 0.0)),
                }
            },
        )()

        # Act
        with patch(
            "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.omni.kit.commands.execute"
        ) as execute:
            with (
                patch(
                    "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.omni.usd.get_context",
                    return_value=_Context(prim.GetStage()),
                ),
                patch(
                    "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.get_schema_prim",
                    return_value=(None, schema_prim),
                ),
            ):
                result = seed_current_animated_attr_from_legacy("primvars:particle:minSize:x", "", str(prim.GetPath()))

        # Assert
        self.assertTrue(result)
        execute.assert_called_once()
        _, kwargs = execute.call_args
        self.assertEqual(kwargs["curve_id"], "particle:minSize:x")
        self.assertEqual([key.time for key in kwargs["curve"].keys], [0.0, 1.0])
        self.assertEqual([key.value for key in kwargs["curve"].keys], [25.0, 50.0])

    async def test_seed_size_channels_from_matching_legacy_channels(self):
        # Arrange
        prim = self._create_prim()
        min_spawn_attr = prim.CreateAttribute("primvars:particle:minSpawnSize", Sdf.ValueTypeNames.Float2)
        min_target_attr = prim.CreateAttribute("primvars:particle:minTargetSize", Sdf.ValueTypeNames.Float2)
        max_spawn_attr = prim.CreateAttribute("primvars:particle:maxSpawnSize", Sdf.ValueTypeNames.Float2)
        max_target_attr = prim.CreateAttribute("primvars:particle:maxTargetSize", Sdf.ValueTypeNames.Float2)
        min_spawn_attr.Set(Gf.Vec2f(11.0, 12.0))
        min_target_attr.Set(Gf.Vec2f(21.0, 22.0))
        max_spawn_attr.Set(Gf.Vec2f(31.0, 32.0))
        max_target_attr.Set(Gf.Vec2f(41.0, 42.0))
        schema_prim = type(
            "_SchemaPrim",
            (),
            {
                "properties": {
                    "primvars:particle:minSpawnSize": _SchemaAttr(Gf.Vec2f(10.0, 10.0)),
                    "primvars:particle:minTargetSize": _SchemaAttr(Gf.Vec2f(0.0, 0.0)),
                    "primvars:particle:maxSpawnSize": _SchemaAttr(Gf.Vec2f(10.0, 10.0)),
                    "primvars:particle:maxTargetSize": _SchemaAttr(Gf.Vec2f(0.0, 0.0)),
                }
            },
        )()
        expected_values_by_attr = {
            "primvars:particle:minSize:x": [11.0, 21.0],
            "primvars:particle:minSize:y": [12.0, 22.0],
            "primvars:particle:maxSize:x": [31.0, 41.0],
            "primvars:particle:maxSize:y": [32.0, 42.0],
        }

        # Act
        with patch(
            "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.omni.kit.commands.execute"
        ) as execute:
            with (
                patch(
                    "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.omni.usd.get_context",
                    return_value=_Context(prim.GetStage()),
                ),
                patch(
                    "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.get_schema_prim",
                    return_value=(None, schema_prim),
                ),
            ):
                results = [
                    seed_current_animated_attr_from_legacy(animated_attr_name, "", str(prim.GetPath()))
                    for animated_attr_name in expected_values_by_attr
                ]

        # Assert
        self.assertEqual(results, [True, True, True, True])
        values_by_curve_id = {
            call.kwargs["curve_id"]: [key.value for key in call.kwargs["curve"].keys] for call in execute.call_args_list
        }
        self.assertEqual(
            values_by_curve_id,
            {
                animated_attr_name.removeprefix("primvars:"): expected_values
                for animated_attr_name, expected_values in expected_values_by_attr.items()
            },
        )

    async def test_seed_rotation_min_and_max_from_matching_legacy_attrs(self):
        # Arrange
        prim = self._create_prim()
        min_spawn_attr = prim.CreateAttribute("primvars:particle:minSpawnRotationSpeed", Sdf.ValueTypeNames.Float)
        min_target_attr = prim.CreateAttribute("primvars:particle:minTargetRotationSpeed", Sdf.ValueTypeNames.Float)
        max_spawn_attr = prim.CreateAttribute("primvars:particle:maxSpawnRotationSpeed", Sdf.ValueTypeNames.Float)
        max_target_attr = prim.CreateAttribute("primvars:particle:maxTargetRotationSpeed", Sdf.ValueTypeNames.Float)
        min_spawn_attr.Set(5.0)
        min_target_attr.Set(9.0)
        max_spawn_attr.Set(15.0)
        max_target_attr.Set(19.0)
        schema_prim = type(
            "_SchemaPrim",
            (),
            {
                "properties": {
                    "primvars:particle:minSpawnRotationSpeed": _SchemaAttr(0.0),
                    "primvars:particle:minTargetRotationSpeed": _SchemaAttr(0.0),
                    "primvars:particle:maxSpawnRotationSpeed": _SchemaAttr(0.0),
                    "primvars:particle:maxTargetRotationSpeed": _SchemaAttr(0.0),
                }
            },
        )()

        # Act
        with patch(
            "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.omni.kit.commands.execute"
        ) as execute:
            with (
                patch(
                    "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.omni.usd.get_context",
                    return_value=_Context(prim.GetStage()),
                ),
                patch(
                    "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.get_schema_prim",
                    return_value=(None, schema_prim),
                ),
            ):
                min_result = seed_current_animated_attr_from_legacy(
                    "primvars:particle:minRotationSpeed", "", str(prim.GetPath())
                )
                max_result = seed_current_animated_attr_from_legacy(
                    "primvars:particle:maxRotationSpeed", "", str(prim.GetPath())
                )

        # Assert
        self.assertTrue(min_result)
        self.assertTrue(max_result)
        values_by_curve_id = {
            call.kwargs["curve_id"]: [key.value for key in call.kwargs["curve"].keys] for call in execute.call_args_list
        }
        self.assertEqual(
            values_by_curve_id,
            {
                "particle:minRotationSpeed": [5.0, 9.0],
                "particle:maxRotationSpeed": [15.0, 19.0],
            },
        )

    async def test_seed_gradient_from_legacy_uses_start_and_end_colors(self):
        # Arrange
        prim = self._create_prim()
        spawn_attr = prim.CreateAttribute("primvars:particle:minSpawnColor", Sdf.ValueTypeNames.Color4f)
        target_attr = prim.CreateAttribute("primvars:particle:minTargetColor", Sdf.ValueTypeNames.Color4f)
        spawn_attr.Set(Gf.Vec4f(1.0, 0.5, 0.25, 1.0))
        target_attr.Set(Gf.Vec4f(0.0, 0.25, 0.5, 0.75))
        schema_prim = type(
            "_SchemaPrim",
            (),
            {
                "properties": {
                    "primvars:particle:minSpawnColor": _SchemaAttr(Gf.Vec4f(1.0, 1.0, 1.0, 1.0)),
                    "primvars:particle:minTargetColor": _SchemaAttr(Gf.Vec4f(1.0, 1.0, 1.0, 0.0)),
                }
            },
        )()

        # Act
        with patch(
            "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.omni.kit.commands.execute"
        ) as execute:
            with (
                patch(
                    "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.omni.usd.get_context",
                    return_value=_Context(prim.GetStage()),
                ),
                patch(
                    "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.get_schema_prim",
                    return_value=(None, schema_prim),
                ),
            ):
                result = seed_current_animated_attr_from_legacy("primvars:particle:minColor", "", str(prim.GetPath()))

        # Assert
        self.assertTrue(result)
        execute.assert_called_once()
        command_name, kwargs = execute.call_args.args[0], execute.call_args.kwargs
        self.assertEqual(command_name, "SetGradientPrimvars")
        self.assertEqual(kwargs["base_name"], "primvars:particle:minColor")
        self.assertEqual(kwargs["times"], [0.0, 1.0])
        self.assertEqual(kwargs["values"], [(1.0, 0.5, 0.25, 1.0), (0.0, 0.25, 0.5, 0.75)])

    async def test_seed_max_gradient_from_matching_legacy_colors(self):
        # Arrange
        prim = self._create_prim()
        spawn_attr = prim.CreateAttribute("primvars:particle:maxSpawnColor", Sdf.ValueTypeNames.Color4f)
        target_attr = prim.CreateAttribute("primvars:particle:maxTargetColor", Sdf.ValueTypeNames.Color4f)
        spawn_attr.Set(Gf.Vec4f(0.1, 0.2, 0.3, 1.0))
        target_attr.Set(Gf.Vec4f(0.7, 0.8, 0.9, 0.5))
        schema_prim = type(
            "_SchemaPrim",
            (),
            {
                "properties": {
                    "primvars:particle:maxSpawnColor": _SchemaAttr(Gf.Vec4f(1.0, 1.0, 1.0, 1.0)),
                    "primvars:particle:maxTargetColor": _SchemaAttr(Gf.Vec4f(1.0, 1.0, 1.0, 0.0)),
                }
            },
        )()

        # Act
        with patch(
            "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.omni.kit.commands.execute"
        ) as execute:
            with (
                patch(
                    "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.omni.usd.get_context",
                    return_value=_Context(prim.GetStage()),
                ),
                patch(
                    "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.get_schema_prim",
                    return_value=(None, schema_prim),
                ),
            ):
                result = seed_current_animated_attr_from_legacy("primvars:particle:maxColor", "", str(prim.GetPath()))

        # Assert
        self.assertTrue(result)
        execute.assert_called_once()
        command_name, kwargs = execute.call_args.args[0], execute.call_args.kwargs
        self.assertEqual(command_name, "SetGradientPrimvars")
        self.assertEqual(kwargs["base_name"], "primvars:particle:maxColor")
        self.assertEqual(kwargs["times"], [0.0, 1.0])
        self.assertEqual(
            [[round(component, 6) for component in value] for value in kwargs["values"]],
            [[0.1, 0.2, 0.3, 1.0], [0.7, 0.8, 0.9, 0.5]],
        )

    async def test_current_attr_seed_does_not_seed_sibling_attrs(self):
        # Arrange
        prim = self._create_prim()
        size_attr = prim.CreateAttribute("primvars:particle:minSpawnSize", Sdf.ValueTypeNames.Float2)
        size_attr.Set(Gf.Vec2f(25.0, 10.0))
        target_attr = prim.CreateAttribute("primvars:particle:minTargetSize", Sdf.ValueTypeNames.Float2)
        target_attr.Set(Gf.Vec2f(50.0, 20.0))
        schema_prim = type(
            "_SchemaPrim",
            (),
            {
                "properties": {
                    "primvars:particle:minSpawnSize": _SchemaAttr(Gf.Vec2f(10.0, 10.0)),
                    "primvars:particle:minTargetSize": _SchemaAttr(Gf.Vec2f(0.0, 0.0)),
                }
            },
        )()

        # Act
        with patch(
            "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.omni.kit.commands.execute"
        ) as execute:
            with (
                patch(
                    "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.omni.usd.get_context",
                    return_value=_Context(prim.GetStage()),
                ),
                patch(
                    "lightspeed.trex.properties_pane.particle.widget.legacy_support_helper.get_schema_prim",
                    return_value=(None, schema_prim),
                ),
            ):
                result = seed_current_animated_attr_from_legacy("primvars:particle:minSize:x", "", str(prim.GetPath()))

        # Assert
        self.assertTrue(result)
        curve_ids = [call.kwargs.get("curve_id") for call in execute.call_args_list]
        self.assertEqual(curve_ids, ["particle:minSize:x"])
