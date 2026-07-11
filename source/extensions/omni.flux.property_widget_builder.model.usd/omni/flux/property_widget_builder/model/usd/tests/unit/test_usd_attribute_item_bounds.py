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

from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

import omni.kit.undo
import omni.kit.test
import omni.usd
from omni.flux.property_widget_builder.model.usd import (
    BoundsAdapter,
    USDAttrListItem,
    USDAttributeItem,
    USDAttributeXformItem,
    USDLogicalGroupOutletItem,
)
from omni.flux.property_widget_builder.model.usd import items as _items_module
from omni.flux.property_widget_builder.model.usd.items import VirtualUSDAttributeItem
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Gf, Sdf, UsdGeom


class _UiMetadataAdapter(BoundsAdapter):
    def _normalize_bounds_step_data(self, metadata_data):
        if not isinstance(metadata_data, dict):
            return None
        return {
            "soft_min": metadata_data.get("soft_min"),
            "soft_max": metadata_data.get("soft_max"),
            "hard_min": metadata_data.get("hard_min"),
            "hard_max": metadata_data.get("hard_max"),
            "step": metadata_data.get("ui_step"),
        }


def _make_item(stage, ui_metadata=None, custom_data=None, bounds_adapter=None):
    """Create a float attribute item for bounds tests.

    Args:
        stage: Stage where the test prim and attribute are created.
        ui_metadata: Optional UI metadata passed to the item.
        custom_data: Optional custom data authored on the attribute.
        bounds_adapter: Optional bounds adapter injected into the item.

    Returns:
        USD attribute item wrapping the created test attribute.
    """

    prim = stage.DefinePrim("/BoundsTestPrim")
    attr = prim.CreateAttribute("testFloat", Sdf.ValueTypeNames.Float)
    attr.Set(0.0)
    if custom_data is not None:
        attr.SetMetadata("customData", custom_data)
    return USDAttributeItem(
        context_name="",
        attribute_paths=[Sdf.Path("/BoundsTestPrim.testFloat")],
        ui_metadata=ui_metadata,
        bounds_adapter=bounds_adapter or (_UiMetadataAdapter(ui_metadata) if ui_metadata is not None else None),
    )


def _make_xform_override_test_stage(stage, prim_path="/XformOverrideTest"):
    """Create a composed xform prim from a weak layer with an empty root edit target."""
    root_layer = stage.GetRootLayer()
    weak_layer = Sdf.Layer.CreateAnonymous("weak_xform.usda")
    root_layer.subLayerPaths.append(weak_layer.identifier)
    stage.SetEditTarget(weak_layer)

    prim = stage.DefinePrim(prim_path, "Xform")
    xformable = UsdGeom.Xformable(prim)
    translate_op = xformable.AddTranslateOp()
    translate_op.Set(Gf.Vec3d(1.0, 0.0, 0.0))
    rotate_op = xformable.AddRotateXYZOp()
    rotate_op.Set(Gf.Vec3f(0.0, 10.0, 0.0))
    scale_op = xformable.AddScaleOp()
    scale_op.Set(Gf.Vec3f(1.0, 2.0, 1.0))

    stage.SetEditTarget(root_layer)
    return (
        root_layer,
        translate_op.GetAttr().GetPath(),
        [
            translate_op.GetAttr().GetPath(),
            rotate_op.GetAttr().GetPath(),
            scale_op.GetAttr().GetPath(),
            xformable.GetXformOpOrderAttr().GetPath(),
        ],
    )


class _FixedBoundsAdapter(BoundsAdapter):
    def _normalize_bounds_step_data(self, metadata_data):
        if isinstance(metadata_data, dict) and metadata_data.get("force"):
            return {"soft_min": 1.0, "soft_max": 2.0, "hard_min": 0.0, "hard_max": 3.0, "step": None}
        return super()._normalize_bounds_step_data(metadata_data)


class _LimitsOnlyAdapter(BoundsAdapter):
    def _normalize_bounds_step_data(self, metadata_data):
        if not isinstance(metadata_data, dict):
            return None
        limits = metadata_data.get("limits")
        if not isinstance(limits, dict):
            return None
        soft_block = limits.get("soft")
        hard_block = limits.get("hard")
        soft_min = soft_block.get("minimum") if isinstance(soft_block, dict) else None
        soft_max = soft_block.get("maximum") if isinstance(soft_block, dict) else None
        hard_min = hard_block.get("minimum") if isinstance(hard_block, dict) else None
        hard_max = hard_block.get("maximum") if isinstance(hard_block, dict) else None
        step = limits.get("step")
        min_val = soft_min if soft_min is not None else hard_min
        max_val = soft_max if soft_max is not None else hard_max
        if min_val is None and max_val is None and step is None:
            return None
        return {
            "soft_min": min_val,
            "soft_max": max_val,
            "hard_min": hard_min,
            "hard_max": hard_max,
            "step": step,
        }


class TestUSDAttributeItemBounds(omni.kit.test.AsyncTestCase):
    """Tests for the single-source adapter bounds/step contract."""

    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()

    async def tearDown(self):
        if self.context:
            await self.context.close_stage_async()
        self.context = None
        self.stage = None

    async def test_ui_metadata_soft_and_hard_bounds(self):
        # Arrange
        item = _make_item(
            self.stage,
            ui_metadata={
                "soft_min": 0.0,
                "soft_max": 100.0,
                "hard_min": -10.0,
                "hard_max": 110.0,
            },
        )

        # Act
        result = item.get_min_max_bounds()

        # Assert
        self.assertEqual(result, (0.0, 100.0, -10.0, 110.0))

    async def test_ui_metadata_hard_only(self):
        # Arrange
        item = _make_item(
            self.stage,
            ui_metadata={
                "hard_min": -20.0,
                "hard_max": 200.0,
            },
        )

        # Act
        result = item.get_min_max_bounds()

        # Assert
        self.assertEqual(result, (-20.0, 200.0, -20.0, 200.0))

    async def test_ui_metadata_none_returns_none(self):
        # Arrange
        item = _make_item(self.stage, ui_metadata=None)

        # Act
        result = item.get_min_max_bounds()

        # Assert
        self.assertIsNone(result)

    async def test_ui_metadata_empty_dict_returns_none(self):
        """Empty ui_metadata dict (no bound keys): returns None."""
        # Arrange
        item = _make_item(self.stage, ui_metadata={})

        # Act
        result = item.get_min_max_bounds()

        # Assert
        self.assertIsNone(result)

    async def test_set_display_attr_names_uses_empty_name_when_display_list_is_short(self):
        # Arrange
        item = _make_item(self.stage)

        # Act
        item.set_display_attr_names([])

        # Assert
        self.assertEqual("", item.name_models[0].get_value_as_string())

    async def test_set_display_attr_names_tooltip_keeps_default_tooltip_when_display_list_is_short(self):
        # Arrange
        item = _make_item(self.stage)

        # Act
        item.set_display_attr_names_tooltip([])

        # Assert
        self.assertEqual("testFloat", item.name_models[0].get_tool_tip())

    async def test_delete_all_overrides_notifies_subscribers_after_deletion(self):
        # Arrange
        item = _make_item(self.stage)
        callback = Mock()
        subscription = item.subscribe_override_removed(callback)

        with patch.object(_items_module, "_delete_all_overrides") as delete_all_overrides_mock:
            # Act
            item.delete_all_overrides()

        # Assert
        self.assertIsNotNone(subscription)
        delete_all_overrides_mock.assert_called_once()
        self.assertEqual("", delete_all_overrides_mock.call_args.kwargs["context_name"])
        callback.assert_called_once_with()

    async def test_delete_layer_override_notifies_subscribers_after_deletion(self):
        # Arrange
        item = _make_item(self.stage)
        layer = self.stage.GetRootLayer()
        callback = Mock()
        subscription = item.subscribe_override_removed(callback)

        with patch.object(_items_module, "_delete_layer_override") as delete_layer_override_mock:
            # Act
            item.delete_layer_override(layer)

        # Assert
        self.assertIsNotNone(subscription)
        delete_layer_override_mock.assert_called_once()
        self.assertEqual(layer, delete_layer_override_mock.call_args.args[0])
        self.assertEqual("", delete_layer_override_mock.call_args.kwargs["context_name"])
        callback.assert_called_once_with()

    async def test_xform_item_groups_related_property_specs_under_one_layer_override(self):
        """Xform rows should expose one logical layer override for all related xform specs."""

        # Arrange
        prim = self.stage.DefinePrim("/XformOverrideTest", "Xform")
        with tempfile.TemporaryDirectory() as temp_dir:
            layer = Sdf.Layer.CreateNew(str(Path(temp_dir) / "xform_override.usda"))
            self.stage.GetRootLayer().subLayerPaths.append(layer.identifier)
            self.stage.SetEditTarget(layer)

            xformable = UsdGeom.Xformable(prim)
            translate_op = xformable.AddTranslateOp()
            translate_op.Set(Gf.Vec3d(1.0, 0.0, 0.0))
            rotate_op = xformable.AddRotateXYZOp()
            rotate_op.Set(Gf.Vec3f(0.0, 10.0, 0.0))
            scale_op = xformable.AddScaleOp()
            scale_op.Set(Gf.Vec3f(1.0, 2.0, 1.0))
            related_paths = [
                translate_op.GetAttr().GetPath(),
                rotate_op.GetAttr().GetPath(),
                scale_op.GetAttr().GetPath(),
                xformable.GetXformOpOrderAttr().GetPath(),
            ]

            item = USDAttributeXformItem("", [translate_op.GetAttr().GetPath()], related_attribute_paths=related_paths)

            # Act
            property_stack = item.get_property_stack()
            override_layers = item.get_layer_override_layers({layer.identifier})

            # Assert
            self.assertEqual(
                {
                    Sdf.Path("/XformOverrideTest.xformOp:translate"),
                    Sdf.Path("/XformOverrideTest.xformOp:rotateXYZ"),
                    Sdf.Path("/XformOverrideTest.xformOp:scale"),
                    Sdf.Path("/XformOverrideTest.xformOpOrder"),
                },
                {spec.path for spec in property_stack if spec.layer.identifier == layer.identifier},
            )
            self.assertTrue(item.is_overriden)
            self.assertEqual([layer], override_layers)

    async def test_xform_item_end_edit_without_value_change_does_not_author_overrides(self):
        """Focus-only xform edits should not author override specs."""
        # Arrange
        omni.kit.undo.clear_stack()
        omni.kit.undo.clear_history()
        target_layer, translate_path, related_paths = _make_xform_override_test_stage(self.stage)
        item = USDAttributeXformItem("", [translate_path], related_attribute_paths=related_paths)

        try:
            # Act
            item.value_models[0].begin_edit()
            item.value_models[0].end_edit()

            # Assert
            self.assertEqual([], [path for path in related_paths if target_layer.GetPropertyAtPath(path) is not None])
            self.assertFalse(
                [entry for entry in omni.kit.undo.get_history().values() if entry.name == "ChangeProperty"]
            )
        finally:
            omni.kit.undo.clear_stack()
            omni.kit.undo.clear_history()

    async def test_xform_item_value_write_authors_related_overrides_in_one_undo(self):
        """Changing one xform channel should author the full logical xform override set."""
        # Arrange
        omni.kit.undo.clear_stack()
        omni.kit.undo.clear_history()
        target_layer, translate_path, related_paths = _make_xform_override_test_stage(self.stage)
        item = USDAttributeXformItem("", [translate_path], related_attribute_paths=related_paths)

        try:
            # Act
            item.value_models[0].set_value(2.0)

            # Assert
            self.assertEqual(
                set(related_paths),
                {path for path in related_paths if target_layer.GetPropertyAtPath(path) is not None},
            )

            omni.kit.undo.undo()

            self.assertEqual([], [path for path in related_paths if target_layer.GetPropertyAtPath(path) is not None])
        finally:
            omni.kit.undo.clear_stack()
            omni.kit.undo.clear_history()

    async def test_attr_list_item_value_write_uses_common_write_path(self):
        """List-backed attribute writes should keep working through the shared write transaction."""
        # Arrange
        prim = self.stage.DefinePrim("/ListAttributeTest")
        attr = prim.CreateAttribute("choice", Sdf.ValueTypeNames.Token)
        attr.Set("A")
        item = USDAttrListItem(
            "",
            [Sdf.Path("/ListAttributeTest.choice")],
            default_value="A",
            options=["A", "B"],
            value_type_name=Sdf.ValueTypeNames.Token,
        )

        # Act
        item.value_models[0].set_value("B")

        # Assert
        self.assertEqual("B", attr.Get())

    async def test_ui_metadata_vector_bounds_are_preserved(self):
        """Vector-like ui metadata bounds should be preserved for widget-level scalar indexing."""
        # Arrange
        item = _make_item(
            self.stage,
            ui_metadata={
                "soft_min": Gf.Vec2f(1.0, 2.0),
                "soft_max": Gf.Vec2f(3.0, 9.0),
                "hard_min": Gf.Vec2f(-5.0, -1.0),
                "hard_max": Gf.Vec2f(12.0, 8.0),
            },
        )

        # Act
        result = item.get_min_max_bounds()

        # Assert
        self.assertEqual(result, (Gf.Vec2f(1.0, 2.0), Gf.Vec2f(3.0, 9.0), Gf.Vec2f(-5.0, -1.0), Gf.Vec2f(12.0, 8.0)))

    async def test_get_min_max_bounds_ignores_attr_custom_data(self):
        """Item should no longer fall back to attr metadata."""
        # Arrange
        item = _make_item(
            self.stage,
            ui_metadata={},
            custom_data={"range": {"min": 0.0, "max": 100.0}},
        )

        # Act
        result = item.get_min_max_bounds()

        # Assert
        self.assertIsNone(result)

    async def test_get_min_max_bounds_returns_none_when_no_data(self):
        # Arrange
        item = _make_item(self.stage)

        # Act
        result = item.get_min_max_bounds()

        # Assert
        self.assertIsNone(result)

    async def test_get_min_max_bounds_uses_injected_adapter_source(self):
        # Arrange
        prim = self.stage.DefinePrim("/BoundsAdapterPrim")
        attr = prim.CreateAttribute("testFloat", Sdf.ValueTypeNames.Float)
        attr.Set(0.0)
        attr.SetMetadata("customData", {"range": {"min": -10.0, "max": 10.0}})
        item = USDAttributeItem(
            context_name="",
            attribute_paths=[Sdf.Path("/BoundsAdapterPrim.testFloat")],
            ui_metadata={"force": True},
            bounds_adapter=_FixedBoundsAdapter({"force": True}),
        )

        # Act
        result = item.get_min_max_bounds()

        # Assert
        self.assertEqual(result, (1.0, 2.0, 0.0, 3.0))

    async def test_get_step_value_from_injected_adapter(self):
        # Arrange
        item = _make_item(
            self.stage,
            ui_metadata={"ui_step": 0.5},
            custom_data={"limits": {"hard": {"step": 2.0}}, "ui:step": 3.0},
        )

        # Act
        step = item.get_step_value()

        # Assert
        self.assertEqual(step, 0.5)

    async def test_get_step_value_ignores_attr_custom_data(self):
        # Arrange
        item = _make_item(
            self.stage,
            ui_metadata={},
            custom_data={"range": {"min": 0.0, "max": 10.0}, "ui:step": 0.25},
        )

        # Act
        step = item.get_step_value()

        # Assert
        self.assertIsNone(step)

    async def test_get_min_max_bounds_uses_limits_with_injected_source_adapter(self):
        # Arrange
        prim = self.stage.DefinePrim("/BoundsAdapterLimitsPrim")
        attr = prim.CreateAttribute("testFloat", Sdf.ValueTypeNames.Float)
        attr.Set(0.0)
        attr.SetMetadata("customData", {"limits": {"hard": {"minimum": 0.0, "maximum": 42.0}}})
        item = USDAttributeItem(
            context_name="",
            attribute_paths=[Sdf.Path("/BoundsAdapterLimitsPrim.testFloat")],
            ui_metadata={"limits": {"hard": {"minimum": 0.0, "maximum": 42.0}}},
            bounds_adapter=_LimitsOnlyAdapter({"limits": {"hard": {"minimum": 0.0, "maximum": 42.0}}}),
        )

        # Act
        result = item.get_min_max_bounds()

        # Assert
        self.assertEqual(result, (0.0, 42.0, 0.0, 42.0))

    async def test_get_step_value_uses_limits_with_injected_source_adapter(self):
        # Arrange
        prim = self.stage.DefinePrim("/BoundsAdapterLimitsStepPrim")
        attr = prim.CreateAttribute("testFloat", Sdf.ValueTypeNames.Float)
        attr.Set(0.0)
        attr.SetMetadata("customData", {"limits": {"step": 0.125}})
        payload = {"limits": {"step": 0.125}}
        item = USDAttributeItem(
            context_name="",
            attribute_paths=[Sdf.Path("/BoundsAdapterLimitsStepPrim.testFloat")],
            ui_metadata=payload,
            bounds_adapter=_LimitsOnlyAdapter(payload),
        )

        # Act
        step = item.get_step_value()

        # Assert
        self.assertEqual(step, 0.125)

    async def test_virtual_item_uses_injected_bounds_adapter(self):
        # Arrange
        self.stage.DefinePrim("/VirtualBoundsPrim")
        payload = {"limits": {"hard": {"minimum": 1.0, "maximum": 10.0}, "step": 0.5}}
        item = VirtualUSDAttributeItem(
            context_name="",
            attribute_paths=[Sdf.Path("/VirtualBoundsPrim.virtualFloat")],
            value_type_name=Sdf.ValueTypeNames.Float,
            default_value=0.0,
            bounds_adapter=_LimitsOnlyAdapter(payload),
        )

        # Act
        bounds = item.get_min_max_bounds()
        step = item.get_step_value()

        # Assert
        self.assertEqual(bounds, (1.0, 10.0, 1.0, 10.0))
        self.assertEqual(step, 0.5)

    async def test_virtual_item_allows_missing_bounds_step_metadata(self):
        # Arrange
        self.stage.DefinePrim("/VirtualNoBoundsPrim")
        item = VirtualUSDAttributeItem(
            context_name="",
            attribute_paths=[Sdf.Path("/VirtualNoBoundsPrim.virtualFloat")],
            value_type_name=Sdf.ValueTypeNames.Float,
            default_value=0.0,
            bounds_adapter=_LimitsOnlyAdapter({"unexpected": "metadata"}),
        )

        # Act
        bounds = item.get_min_max_bounds()
        step = item.get_step_value()

        # Assert
        self.assertIsNone(bounds)
        self.assertIsNone(step)

    async def test_logical_group_outlet_default_attrs_clear_owned_references(self):
        # Arrange
        item = USDLogicalGroupOutletItem(
            edit_group_layout={"display_name": "Particle Size"},
            context_name="",
            target_paths=["/Particle"],
        )
        item.pre_open_callback = lambda open_editor_fn: open_editor_fn()

        # Act
        _reset_default_attrs(item)

        # Assert
        self.assertIsNone(item.edit_group_layout)
        self.assertIsNone(item.context_name)
        self.assertIsNone(item.target_paths)
        self.assertIsNone(item.pre_open_callback)
        self.assertIsNone(item._name_models)
        self.assertIsNone(item._value_models)

    async def test_attribute_item_default_attrs_clear_edit_group_references(self):
        # Arrange
        item = _make_item(self.stage)
        item.edit_group_layout = {"display_name": "Particle Size"}
        item.edit_group_path = "size"
        item.pre_open_callback = lambda open_editor_fn: open_editor_fn()

        # Act
        _reset_default_attrs(item)

        # Assert
        self.assertIsNone(item.edit_group_layout)
        self.assertIsNone(item.edit_group_path)
        self.assertIsNone(item.pre_open_callback)
