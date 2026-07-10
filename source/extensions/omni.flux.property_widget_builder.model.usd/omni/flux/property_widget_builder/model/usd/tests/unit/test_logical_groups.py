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

from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import Mock, patch

import omni.kit.test
import omni.usd
from omni.flux.property_widget_builder.model.usd import items as _items_module
from omni.flux.property_widget_builder.model.usd import (
    USDAttributeItem,
    USDAttributeXformItem,
    USDDelegate,
    USDLogicalGroupOutletItem,
    USDRelationshipItem,
)
from omni.flux.property_widget_builder.model.usd.logical_group_constants import CURVE_LOGICAL_GROUP_DEFINITION
from omni.flux.property_widget_builder.model.usd.logical_group_constants import CURVE_LOGICAL_SUFFIXES
from omni.flux.property_widget_builder.model.usd.logical_group_constants import GRADIENT_LOGICAL_GROUP_DEFINITION
from omni.flux.property_widget_builder.model.usd.logical_row import LogicalRowState
from omni.flux.property_widget_builder.model.usd.logical_row import is_logical_group_mixed
from omni.flux.property_widget_builder.widget.tree.item_model import ItemGroupNameModel
from omni.flux.property_widget_builder.model.usd.field_builders import ALL_FIELD_BUILDERS, GRADIENT_FIELD_BUILDERS
from omni.flux.property_widget_builder.model.usd.field_builders.curve import _claim_curves, _curve_attr_names
from omni.flux.property_widget_builder.model.usd.field_builders.gradient import _claim_gradients
from pxr import Gf, Sdf, UsdGeom, Vt


def _attr_path(prim_path: str, name: str) -> Sdf.Path:
    return Sdf.Path(f"{prim_path}.{name}")


class _ResetModel:
    is_default = False
    is_mixed = False
    is_overriden = True

    def __init__(self):
        self.reset_count = 0

    def reset_default_value(self):
        self.reset_count += 1


class _Item:
    def __init__(self, *value_models):
        self.value_models = list(value_models)


class _LogicalItem:
    value_models = []

    def __init__(self, state: LogicalRowState):
        self._state = state
        self.reset_row_value = Mock()
        self.delete_row_overrides = Mock()

    def get_row_state(self) -> LogicalRowState:
        return self._state


class TestLogicalGroups(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        self._stage = self._context.get_stage()
        self._prim_path = "/World/ParticleA"
        self._other_prim_path = "/World/ParticleB"
        self._base_name = "primvars:particle:color"
        self._curve_base_name = "primvars:particle:size:x"

        for prim_path in (self._prim_path, self._other_prim_path):
            prim = self._stage.DefinePrim(prim_path, "Xform")
            times = prim.CreateAttribute(f"{self._base_name}:times", Sdf.ValueTypeNames.DoubleArray)
            values = prim.CreateAttribute(f"{self._base_name}:values", Sdf.ValueTypeNames.Color4fArray)
            times.Set(Vt.DoubleArray([0.0, 1.0]))
            values.Set(Vt.Vec4fArray([Gf.Vec4f(1, 0, 0, 1), Gf.Vec4f(0, 0, 1, 1)]))
            times.SetCustomDataByKey("default", Vt.DoubleArray([0.0, 1.0]))
            values.SetCustomDataByKey(
                "default",
                Vt.Vec4fArray([Gf.Vec4f(1, 0, 0, 1), Gf.Vec4f(0, 0, 1, 1)]),
            )

    async def tearDown(self):
        await self._context.close_stage_async()

    def _curve_attr_value(self, suffix: str):
        if suffix in {"times", "values", "inTangentTimes", "inTangentValues", "outTangentTimes", "outTangentValues"}:
            return Vt.DoubleArray([0.0, 1.0])
        if suffix in {"inTangentTypes", "outTangentTypes"}:
            return Vt.TokenArray(["linear", "linear"])
        if suffix == "tangentBrokens":
            return Vt.BoolArray([False, False])
        if suffix in {"preInfinity", "postInfinity"}:
            return "constant"
        raise ValueError(f"Unknown curve suffix: {suffix}")

    def _curve_attr_type(self, suffix: str) -> Sdf.ValueTypeName:
        if suffix in {"times", "values", "inTangentTimes", "inTangentValues", "outTangentTimes", "outTangentValues"}:
            return Sdf.ValueTypeNames.DoubleArray
        if suffix in {"inTangentTypes", "outTangentTypes"}:
            return Sdf.ValueTypeNames.TokenArray
        if suffix == "tangentBrokens":
            return Sdf.ValueTypeNames.BoolArray
        if suffix in {"preInfinity", "postInfinity"}:
            return Sdf.ValueTypeNames.Token
        raise ValueError(f"Unknown curve suffix: {suffix}")

    def _create_curve_attrs(self) -> None:
        for prim_path in (self._prim_path, self._other_prim_path):
            prim = self._stage.GetPrimAtPath(prim_path)
            for suffix in CURVE_LOGICAL_SUFFIXES:
                attr = prim.CreateAttribute(f"{self._curve_base_name}:{suffix}", self._curve_attr_type(suffix))
                attr.Set(self._curve_attr_value(suffix))

    def _registry_claim_result(self, items: list[USDAttributeItem], target: USDAttributeItem):
        """Return the first composed field-builder registry claim for the target item."""
        for field_builder in reversed(ALL_FIELD_BUILDERS):
            result = field_builder.claim_func(items)
            if target in result.primary or target in result.companions:
                return field_builder, result
        return None, None

    async def test_xform_row_owned_attributes_preserve_full_xform_group(self):
        # Arrange
        prim = self._stage.GetPrimAtPath(self._prim_path)
        xformable = UsdGeom.Xformable(prim)
        translate_attr = xformable.AddTranslateOp().GetAttr()
        rotate_attr = xformable.AddRotateXYZOp().GetAttr()
        scale_attr = xformable.AddScaleOp().GetAttr()
        item = USDAttributeXformItem(self._context.get_name(), [translate_attr.GetPath()])

        # Act
        owned_attributes = item.get_owned_attributes()
        owned_paths = set()
        for attribute in owned_attributes:
            owned_paths.add(attribute.GetPath())

        # Assert
        self.assertEqual(
            owned_paths,
            {
                translate_attr.GetPath(),
                rotate_attr.GetPath(),
                scale_attr.GetPath(),
                xformable.GetXformOpOrderAttr().GetPath(),
            },
        )

    async def test_relationship_row_owned_properties_include_relationship(self):
        # Arrange
        prim = self._stage.GetPrimAtPath(self._prim_path)
        relationship = prim.CreateRelationship("inputs:target")
        item = USDRelationshipItem(self._context.get_name(), [relationship.GetPath()])

        # Act
        owned_properties = item.get_owned_properties()
        owned_paths = set()
        for prop in owned_properties:
            owned_paths.add(prop.GetPath())

        # Assert
        self.assertEqual(owned_paths, {relationship.GetPath()})

    def _make_attr_item(self, attr_name: str, value_type_name: Sdf.ValueTypeName) -> USDAttributeItem:
        return USDAttributeItem(
            "",
            [_attr_path(self._prim_path, attr_name), _attr_path(self._other_prim_path, attr_name)],
            value_type_name=value_type_name,
        )

    def _make_claimed_curve_outlet(self) -> tuple[USDLogicalGroupOutletItem, dict[str, USDAttributeItem]]:
        self._create_curve_attrs()
        layout = {
            "display_name": "Particle Size",
            "curve_map": {self._curve_base_name: "size/x"},
        }
        outlet = USDLogicalGroupOutletItem(layout, "", [self._prim_path, self._other_prim_path])
        items_by_suffix = {
            suffix: self._make_attr_item(f"{self._curve_base_name}:{suffix}", self._curve_attr_type(suffix))
            for suffix in sorted(CURVE_LOGICAL_SUFFIXES)
        }
        for item in items_by_suffix.values():
            item.edit_group_layout = layout
        _claim_curves([outlet, *items_by_suffix.values()])
        return outlet, items_by_suffix

    async def test_get_target_paths_preserves_attribute_and_outlet_order(self):
        # Arrange
        item = USDAttributeItem(
            "",
            [
                _attr_path(self._other_prim_path, f"{self._base_name}:values"),
                _attr_path(self._prim_path, f"{self._base_name}:values"),
            ],
        )
        edit_group = USDLogicalGroupOutletItem(
            {"display_name": "Curves"},
            "",
            [self._other_prim_path, self._prim_path],
        )

        # Act / Assert
        self.assertEqual(item.get_target_paths(), [self._other_prim_path, self._prim_path])
        self.assertEqual(edit_group.get_target_paths(), [self._other_prim_path, self._prim_path])

    async def test_get_target_paths_returns_empty_outlet_targets(self):
        # Arrange
        edit_group = USDLogicalGroupOutletItem({"display_name": "Curves"}, "", [])

        # Act / Assert
        self.assertEqual(edit_group.get_target_paths(), [])

    async def test_logical_group_mixed_normalizes_equal_gradient_arrays(self):
        # Arrange
        attr_names = [f"{self._base_name}:times", f"{self._base_name}:values"]
        target_paths = [self._prim_path, self._other_prim_path]

        # Act / Assert
        self.assertFalse(is_logical_group_mixed("", target_paths, attr_names))

    async def test_logical_group_mixed_detects_gradient_times_change(self):
        # Arrange
        attr_names = [f"{self._base_name}:times", f"{self._base_name}:values"]
        target_paths = [self._prim_path, self._other_prim_path]

        # Act
        other = self._stage.GetPrimAtPath(self._other_prim_path)
        other.GetAttribute(f"{self._base_name}:times").Set(Vt.DoubleArray([0.0, 0.5, 1.0]))

        # Assert
        self.assertTrue(is_logical_group_mixed("", target_paths, attr_names))

    async def test_logical_group_mixed_detects_gradient_values_change(self):
        # Arrange
        attr_names = [f"{self._base_name}:times", f"{self._base_name}:values"]
        target_paths = [self._prim_path, self._other_prim_path]

        # Act
        other = self._stage.GetPrimAtPath(self._other_prim_path)
        other.GetAttribute(f"{self._base_name}:values").Set(Vt.Vec4fArray([Gf.Vec4f(0, 1, 0, 1), Gf.Vec4f(0, 0, 1, 1)]))

        # Assert
        self.assertTrue(is_logical_group_mixed("", target_paths, attr_names))

    async def test_logical_group_mixed_detects_curve_companion_change(self):
        # Arrange
        self._create_curve_attrs()
        target_paths = [self._prim_path, self._other_prim_path]
        curve_attr_names = _curve_attr_names(self._curve_base_name.removeprefix("primvars:"))

        self.assertFalse(is_logical_group_mixed("", target_paths, curve_attr_names))

        # Act
        other = self._stage.GetPrimAtPath(self._other_prim_path)
        other.GetAttribute(f"{self._curve_base_name}:preInfinity").Set("linear")

        # Assert
        self.assertTrue(is_logical_group_mixed("", target_paths, curve_attr_names))

    async def test_gradient_claim_wires_visible_row_logical_group_items(self):
        # Arrange
        times_item = self._make_attr_item(f"{self._base_name}:times", Sdf.ValueTypeNames.DoubleArray)
        values_item = self._make_attr_item(f"{self._base_name}:values", Sdf.ValueTypeNames.Color4fArray)

        # Act
        result = _claim_gradients([times_item, values_item])

        # Assert
        self.assertEqual(result.primary, [values_item])
        self.assertEqual(result.companions, [times_item])
        self.assertEqual(values_item.logical_group_items, [times_item, values_item])

    async def test_composed_registry_claims_gradient_values_as_primary(self):
        """Composed field builders should route a complete gradient values item to the gradient builder."""
        # Arrange
        times_item = self._make_attr_item(f"{self._base_name}:times", Sdf.ValueTypeNames.DoubleArray)
        values_item = self._make_attr_item(f"{self._base_name}:values", Sdf.ValueTypeNames.Color4fArray)

        # Act
        field_builder, result = self._registry_claim_result([times_item, values_item], values_item)

        # Assert
        self.assertEqual(field_builder, GRADIENT_FIELD_BUILDERS[0])
        self.assertEqual(result.primary, [values_item])

    async def test_composed_registry_claims_gradient_times_as_companion(self):
        """Composed field builders should route a complete gradient times item as a gradient companion."""
        # Arrange
        times_item = self._make_attr_item(f"{self._base_name}:times", Sdf.ValueTypeNames.DoubleArray)
        values_item = self._make_attr_item(f"{self._base_name}:values", Sdf.ValueTypeNames.Color4fArray)

        # Act
        field_builder, result = self._registry_claim_result([times_item, values_item], times_item)

        # Assert
        self.assertEqual(field_builder, GRADIENT_FIELD_BUILDERS[0])
        self.assertEqual(result.companions, [times_item])

    async def test_composed_registry_does_not_claim_plain_float_as_gradient(self):
        """Composed field builders should leave scalar float attributes out of the gradient builder."""
        # Arrange
        item = self._make_attr_item("primvars:particle:mass", Sdf.ValueTypeNames.Float)

        # Act
        field_builder, _ = self._registry_claim_result([item], item)

        # Assert
        self.assertNotEqual(field_builder, GRADIENT_FIELD_BUILDERS[0])

    async def test_composed_registry_does_not_claim_orphan_gradient_values(self):
        """Composed field builders should not route values-only color arrays through the gradient builder."""
        # Arrange
        item = self._make_attr_item("primvars:particle:orphanColor:values", Sdf.ValueTypeNames.Color4fArray)

        # Act
        field_builder, _ = self._registry_claim_result([item], item)

        # Assert
        self.assertNotEqual(field_builder, GRADIENT_FIELD_BUILDERS[0])

    async def test_scalar_row_exposes_own_value_models_attributes_and_state(self):
        # Arrange
        item = self._make_attr_item(f"{self._base_name}:times", Sdf.ValueTypeNames.DoubleArray)

        # Act
        value_models = item.get_owned_value_models()
        attributes = item.get_owned_attributes()
        state = item.get_row_state()

        # Assert
        self.assertEqual(value_models, item.value_models)
        self.assertEqual(
            [str(attr.GetPath()) for attr in attributes],
            [f"{path}.{self._base_name}:times" for path in [self._prim_path, self._other_prim_path]],
        )
        self.assertFalse(state.is_mixed)
        self.assertFalse(state.is_overriden)
        self.assertTrue(state.is_default)

    async def test_gradient_row_exposes_complete_companion_group(self):
        # Arrange
        times_item = self._make_attr_item(f"{self._base_name}:times", Sdf.ValueTypeNames.DoubleArray)
        values_item = self._make_attr_item(f"{self._base_name}:values", Sdf.ValueTypeNames.Color4fArray)
        _claim_gradients([times_item, values_item])

        # Act
        value_models = values_item.get_owned_value_models()
        attributes = values_item.get_owned_attributes()
        attr_names = set()
        for attr in attributes:
            attr_names.add(attr.GetName())

        # Assert
        self.assertEqual(value_models, [*times_item.value_models, *values_item.value_models])
        self.assertEqual(attr_names, {f"{self._base_name}:times", f"{self._base_name}:values"})

    async def test_gradient_row_uses_shared_group_definition_for_ownership_and_mixed_state(self):
        # Arrange
        times_item = self._make_attr_item(f"{self._base_name}:times", Sdf.ValueTypeNames.DoubleArray)
        values_item = self._make_attr_item(f"{self._base_name}:values", Sdf.ValueTypeNames.Color4fArray)
        _claim_gradients([times_item, values_item])
        values_item.logical_group_items = []
        other = self._stage.GetPrimAtPath(self._other_prim_path)

        # Act
        other.GetAttribute(f"{self._base_name}:times").Set(Vt.DoubleArray([0.0, 0.5, 1.0]))
        attributes = values_item.get_owned_attributes()
        state = values_item.get_row_state()

        # Assert
        self.assertEqual(values_item.logical_group_definition, GRADIENT_LOGICAL_GROUP_DEFINITION)
        attr_names = set()
        for attr in attributes:
            attr_names.add(attr.GetName())
        self.assertEqual(attr_names, {f"{self._base_name}:times", f"{self._base_name}:values"})
        self.assertTrue(state.is_mixed)

    async def test_curve_claim_wires_outlet_logical_group_items(self):
        # Arrange
        outlet, items_by_suffix = self._make_claimed_curve_outlet()

        # Act
        result = _claim_curves([outlet, *items_by_suffix.values()])

        # Assert
        expected_group = [items_by_suffix[suffix] for suffix in sorted(CURVE_LOGICAL_SUFFIXES)]
        self.assertEqual(result.primary, [outlet])
        self.assertEqual(set(result.companions), set(items_by_suffix.values()))
        self.assertEqual(outlet.logical_group_items, expected_group)

    async def test_curve_outlet_without_value_model_still_builds_value_column(self):
        # Arrange
        outlet = USDLogicalGroupOutletItem({"display_name": "Curves"}, "", [self._prim_path])
        delegate = USDDelegate()
        builder = object()
        widgets = [object()]

        # Act / Assert
        self.assertEqual(outlet.value_models, [])
        with (
            patch.object(delegate, "get_field_builder", return_value=builder) as get_field_builder_mock,
            patch.object(delegate, "_build_field_widgets", return_value=widgets) as build_field_widgets_mock,
        ):
            self.assertEqual(delegate._build_item_widgets(Mock(), outlet, column_id=1, level=0), widgets)

        get_field_builder_mock.assert_called_once_with(outlet)
        build_field_widgets_mock.assert_called_once_with(builder, outlet)

    async def test_curve_outlet_uses_shared_static_name_model_with_tooltip(self):
        # Arrange
        outlet = USDLogicalGroupOutletItem(
            {"display_name": "Particle Size", "tooltip": "Size curves"},
            "",
            [self._prim_path],
        )

        # Act
        name_model = outlet.name_models[0]

        # Assert
        self.assertIsInstance(name_model, ItemGroupNameModel)
        self.assertEqual(name_model.get_value_as_string(), "Particle Size")
        self.assertEqual(name_model.get_tooltip(), "Size curves")

    async def test_standalone_curve_row_uses_shared_group_definition_for_ownership_and_mixed_state(self):
        # Arrange
        self._create_curve_attrs()
        items_by_suffix = {
            suffix: self._make_attr_item(f"{self._curve_base_name}:{suffix}", self._curve_attr_type(suffix))
            for suffix in sorted(CURVE_LOGICAL_SUFFIXES)
        }
        _claim_curves(list(items_by_suffix.values()))
        values_item = items_by_suffix["values"]
        values_item.logical_group_items = []
        other = self._stage.GetPrimAtPath(self._other_prim_path)

        # Act
        other.GetAttribute(f"{self._curve_base_name}:postInfinity").Set("linear")
        attributes = values_item.get_owned_attributes()
        state = values_item.get_row_state()

        # Assert
        self.assertEqual(values_item.logical_group_definition, CURVE_LOGICAL_GROUP_DEFINITION)
        self.assertEqual(len(attributes), len(CURVE_LOGICAL_SUFFIXES) * 2)
        attr_names = set()
        for attr in attributes:
            attr_names.add(attr.GetName())
        self.assertEqual(attr_names, set(_curve_attr_names("particle:size:x")))
        self.assertTrue(state.is_mixed)

    async def test_curve_outlet_row_exposes_hidden_models_and_backing_attributes(self):
        # Arrange
        outlet, items_by_suffix = self._make_claimed_curve_outlet()
        expected_group = [items_by_suffix[suffix] for suffix in sorted(CURVE_LOGICAL_SUFFIXES)]

        # Act
        value_models = outlet.get_owned_value_models()
        attributes = outlet.get_owned_attributes()

        # Assert
        expected_value_models = []
        for item in expected_group:
            expected_value_models.extend(item.value_models)
        self.assertEqual(value_models, expected_value_models)
        self.assertEqual(len(attributes), len(CURVE_LOGICAL_SUFFIXES) * 2)
        attr_names = set()
        for attr in attributes:
            attr_names.add(attr.GetName())
        self.assertEqual(attr_names, set(_curve_attr_names("particle:size:x")))

    async def test_attribute_row_owned_value_models_api_returns_logical_group_models(self):
        # Arrange
        times_item = self._make_attr_item(f"{self._base_name}:times", Sdf.ValueTypeNames.DoubleArray)
        values_item = self._make_attr_item(f"{self._base_name}:values", Sdf.ValueTypeNames.Color4fArray)
        _claim_gradients([times_item, values_item])

        # Act
        value_models = values_item.get_owned_value_models()

        # Assert
        self.assertEqual(value_models, [*times_item.value_models, *values_item.value_models])

    async def test_curve_outlet_owned_value_models_api_returns_logical_group_models(self):
        # Arrange
        outlet, items_by_suffix = self._make_claimed_curve_outlet()

        # Act
        value_models = outlet.get_owned_value_models()

        # Assert
        expected_value_models = []
        for item in [items_by_suffix[suffix] for suffix in sorted(CURVE_LOGICAL_SUFFIXES)]:
            expected_value_models.extend(item.value_models)
        self.assertEqual(value_models, expected_value_models)

    async def test_attribute_row_pre_open_api_runs_action_without_callback(self):
        # Arrange
        item = self._make_attr_item(f"{self._base_name}:times", Sdf.ValueTypeNames.DoubleArray)
        action = Mock()

        # Act
        item.run_pre_open_callback(action)

        # Assert
        action.assert_called_once_with()

    async def test_attribute_row_pre_open_api_routes_action_through_callback(self):
        # Arrange
        item = self._make_attr_item(f"{self._base_name}:times", Sdf.ValueTypeNames.DoubleArray)
        action = Mock()
        callback = Mock(side_effect=lambda passed_action: passed_action())
        item.pre_open_callback = callback

        # Act
        item.run_pre_open_callback(action)

        # Assert
        callback.assert_called_once_with(action)
        action.assert_called_once_with()

    async def test_curve_outlet_pre_open_api_routes_action_through_callback(self):
        # Arrange
        outlet = USDLogicalGroupOutletItem({"display_name": "Curves"}, "", [self._prim_path])
        action = Mock()
        callback = Mock(side_effect=lambda passed_action: passed_action())
        outlet.pre_open_callback = callback

        # Act
        outlet.run_pre_open_callback(action)

        # Assert
        callback.assert_called_once_with(action)
        action.assert_called_once_with()

    async def test_curve_outlet_row_state_detects_companion_mixed_state(self):
        # Arrange
        outlet, _ = self._make_claimed_curve_outlet()
        other = self._stage.GetPrimAtPath(self._other_prim_path)

        # Act
        other.GetAttribute(f"{self._curve_base_name}:postInfinity").Set("linear")
        state = outlet.get_row_state()

        # Assert
        self.assertTrue(state.is_mixed)
        self.assertFalse(state.is_overriden)
        self.assertFalse(state.is_default)

    async def test_curve_outlet_reset_writes_defaults_without_deleting_overrides(self):
        # Arrange
        outlet, _ = self._make_claimed_curve_outlet()
        attributes = outlet.get_owned_attributes()

        # Act
        with (
            patch.object(_items_module.omni.kit.commands, "execute") as execute_mock,
            patch.object(_items_module.omni.kit.undo, "group", return_value=nullcontext()) as undo_group_mock,
            patch.object(_items_module, "_delete_all_overrides") as delete_all_overrides_mock,
            patch.object(_items_module, "_delete_layer_override") as delete_layer_override_mock,
        ):
            outlet.reset_row_value()

        # Assert
        undo_group_mock.assert_called_once_with()
        self.assertEqual(execute_mock.call_count, len(attributes))
        self.assertTrue(all(call.args[0] == "ChangeProperty" for call in execute_mock.call_args_list))
        executed_prop_paths = set()
        for call in execute_mock.call_args_list:
            executed_prop_paths.add(call.kwargs["prop_path"])
        expected_prop_paths = set()
        for attr in attributes:
            expected_prop_paths.add(attr.GetPath())
        self.assertEqual(executed_prop_paths, expected_prop_paths)
        delete_all_overrides_mock.assert_not_called()
        delete_layer_override_mock.assert_not_called()

    async def test_curve_outlet_delete_row_overrides_touches_all_backing_attributes(self):
        # Arrange
        outlet, _ = self._make_claimed_curve_outlet()

        # Act
        with patch.object(_items_module, "_delete_all_overrides") as delete_all_overrides_mock:
            outlet.delete_row_overrides()

        # Assert
        self.assertEqual(delete_all_overrides_mock.call_count, len(CURVE_LOGICAL_SUFFIXES) * 2)
        deleted_attr_names = set()
        for call in delete_all_overrides_mock.call_args_list:
            deleted_attr_names.add(call.args[0].GetName())
        self.assertEqual(deleted_attr_names, set(_curve_attr_names("particle:size:x")))

    async def test_curve_outlet_layer_delete_uses_backing_attributes(self):
        # Arrange
        outlet, _ = self._make_claimed_curve_outlet()
        layer = self._stage.GetRootLayer()

        # Act
        with patch.object(_items_module, "_delete_layer_override") as delete_layer_override_mock:
            outlet.delete_row_overrides(layer=layer)

        # Assert
        self.assertEqual(delete_layer_override_mock.call_count, len(CURVE_LOGICAL_SUFFIXES) * 2)
        self.assertTrue(all(call.args[0] == layer for call in delete_layer_override_mock.call_args_list))

    async def test_reset_default_uses_complete_logical_group_value_models(self):
        # Arrange
        primary_model = _ResetModel()
        companion_model = _ResetModel()
        primary = self._make_attr_item(f"{self._base_name}:times", Sdf.ValueTypeNames.DoubleArray)
        companion = self._make_attr_item(f"{self._base_name}:values", Sdf.ValueTypeNames.Color4fArray)
        primary._value_models = [primary_model]
        companion._value_models = [companion_model]
        primary.logical_group_items = [primary, companion]

        self.assertEqual(primary.get_owned_value_models(), [primary_model, companion_model])

        # Act
        USDDelegate()._on_reset_item(0, primary)

        # Assert
        self.assertEqual(primary_model.reset_count, 1)
        self.assertEqual(companion_model.reset_count, 1)

    async def test_delegate_reset_routes_through_row_api(self):
        # Arrange
        item = _LogicalItem(LogicalRowState(is_default=False))

        # Act
        USDDelegate()._on_reset_item(0, item)

        # Assert
        item.reset_row_value.assert_called_once_with()

    async def test_delegate_delete_routes_through_row_api(self):
        # Arrange
        item = _LogicalItem(LogicalRowState(is_overriden=True, is_default=False))
        layer = self._stage.GetRootLayer()

        # Act
        USDDelegate()._delete_overrides(item, layer=layer)

        # Assert
        item.delete_row_overrides.assert_called_once_with(layer=layer)
