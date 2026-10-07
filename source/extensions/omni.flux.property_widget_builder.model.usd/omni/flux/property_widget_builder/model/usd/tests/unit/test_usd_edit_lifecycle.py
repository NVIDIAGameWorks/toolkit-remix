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

import asyncio
from contextlib import ExitStack
from unittest.mock import MagicMock, Mock, patch

import omni.kit.app
import omni.kit.undo
import omni.kit.test
import omni.usd
from omni.flux.fcurve.widget import FCurve, FCurveKey, InfinityType, TangentType
from omni.flux.curve_editor.widget.payload import curve_to_payload
from omni.flux.property_widget_builder.model.usd import model as _model_module
from omni.flux.property_widget_builder.model.usd.curve_primvar import PropertyPrimvarCurveModel
from omni.flux.property_widget_builder.model.usd.items import USDAttributeXformItem
from omni.flux.property_widget_builder.model.usd.logical_group_constants import CURVE_LOGICAL_GROUP_DEFINITION
from omni.flux.property_widget_builder.model.usd.item_model.attr_value import UsdAttributeValueModel
from omni.flux.property_widget_builder.model.usd.item_model.attr_value import VirtualUsdAttributeValueModel
from omni.flux.property_widget_builder.model.usd.model import USDModel
from omni.flux.property_widget_builder.widget import ItemGroup
from omni.flux.utils.common.interactive_usd_notices import register_objects_changed_listener as _register_listener
from pxr import Gf, Sdf, UsdGeom

from ...item_model import attr_value


def _make_model(stage, value=0.0):
    prim = stage.DefinePrim("/DragTestPrim")
    attr = prim.CreateAttribute("testFloat", Sdf.ValueTypeNames.Float)
    attr.Set(value)
    return UsdAttributeValueModel(
        context_name="",
        attribute_paths=[Sdf.Path("/DragTestPrim.testFloat")],
        channel_index=0,
    )


def _usd_value(stage):
    return stage.GetPrimAtPath("/DragTestPrim").GetAttribute("testFloat").Get()


def _make_group_edit_item(stage, values):
    """Create a multi-selection xform item and its represented scale attributes."""
    attributes = []
    for index, value in enumerate(values):
        prim = stage.DefinePrim(f"/GroupEditPrim{index}", "Xform")
        attr = UsdGeom.Xformable(prim).AddScaleOp().GetAttr()
        attr.Set(Gf.Vec3f(*value))
        attributes.append(attr)
    return USDAttributeXformItem("", [attr.GetPath() for attr in attributes]), attributes


def _make_group_edit_item_with_related_override(stage):
    """Create a composed xform item whose related specs are absent from the edit target."""
    root_layer = stage.GetRootLayer()
    weak_layer = Sdf.Layer.CreateAnonymous("group_edit_weak.usda")
    root_layer.subLayerPaths.append(weak_layer.identifier)
    stage.SetEditTarget(weak_layer)
    prim = stage.DefinePrim("/GroupEditRelatedPrim", "Xform")
    xformable = UsdGeom.Xformable(prim)
    scale_attr = xformable.AddScaleOp().GetAttr()
    scale_attr.Set(Gf.Vec3f(1.0, 2.0, 3.0))
    rotate_attr = xformable.AddRotateXYZOp().GetAttr()
    rotate_attr.Set(Gf.Vec3f(10.0, 20.0, 30.0))
    stage.SetEditTarget(root_layer)
    item = USDAttributeXformItem(
        "",
        [scale_attr.GetPath()],
        related_attribute_paths=[scale_attr.GetPath(), rotate_attr.GetPath()],
    )
    return item, scale_attr, root_layer, rotate_attr.GetPath()


def _curve(curve_id, key_values):
    return FCurve(id=curve_id, keys=[FCurveKey(time=time, value=value) for time, value in key_values])


def _commit_payload(model: PropertyPrimvarCurveModel, curve: FCurve) -> None:
    model.commit_payload(curve.id, curve_to_payload(curve))


def _curve_attr_name(curve_id: str, suffix: str) -> str:
    return f"primvars:{curve_id}:{suffix}"


def _curve_attr_type(suffix: str):
    if suffix in {"times", "values", "inTangentTimes", "inTangentValues", "outTangentTimes", "outTangentValues"}:
        return Sdf.ValueTypeNames.DoubleArray
    if suffix in {"inTangentTypes", "outTangentTypes"}:
        return Sdf.ValueTypeNames.TokenArray
    if suffix == "tangentBrokens":
        return Sdf.ValueTypeNames.BoolArray
    return Sdf.ValueTypeNames.Token


def _write_curve_to_prim(prim, curve_id: str, curve: FCurve) -> None:
    payload = curve_to_payload(curve)
    for suffix in CURVE_LOGICAL_GROUP_DEFINITION.suffixes:
        attr_name = _curve_attr_name(curve_id, suffix)
        attr = prim.GetAttribute(attr_name)
        if not attr or not attr.IsValid():
            attr = prim.CreateAttribute(attr_name, _curve_attr_type(suffix))
        attr.Set(payload[suffix])


def _snapshot_curve_payload(prim, curve_id: str) -> dict:
    return {
        suffix: prim.GetAttribute(_curve_attr_name(curve_id, suffix)).Get()
        for suffix in CURVE_LOGICAL_GROUP_DEFINITION.suffixes
    }


def _detailed_curve(curve_id: str, middle_time: float | None = None, tangent_seed: float = 0.0) -> FCurve:
    keys = [
        FCurveKey(
            time=0.0,
            value=0.0 + tangent_seed,
            in_tangent_type=TangentType.FLAT,
            out_tangent_type=TangentType.CUSTOM,
            out_tangent_x=0.12 + tangent_seed,
            out_tangent_y=0.04 + tangent_seed,
            tangent_broken=True,
        )
    ]
    if middle_time is not None:
        keys.append(
            FCurveKey(
                time=middle_time,
                value=0.5 + tangent_seed,
                in_tangent_type=TangentType.CUSTOM,
                out_tangent_type=TangentType.CUSTOM,
                in_tangent_x=-0.15 - tangent_seed,
                in_tangent_y=-0.05 - tangent_seed,
                out_tangent_x=0.15 + tangent_seed,
                out_tangent_y=0.05 + tangent_seed,
                tangent_broken=True,
            )
        )
    keys.append(
        FCurveKey(
            time=1.0,
            value=1.0 + tangent_seed,
            in_tangent_type=TangentType.CUSTOM,
            out_tangent_type=TangentType.LINEAR,
            in_tangent_x=-0.12 - tangent_seed,
            in_tangent_y=-0.04 - tangent_seed,
            tangent_broken=True,
        )
    )
    return FCurve(
        id=curve_id,
        keys=keys,
        pre_infinity=InfinityType.LINEAR,
        post_infinity=InfinityType.CONSTANT,
    )


class _TabFieldModel:
    pass


class _FailingCancelValueModel:
    def cancel_property_edit_interaction(self):
        raise RuntimeError("cancel failure")


class _EndingCancelValueModel:
    def __init__(self, callback):
        self._callback = callback

    def cancel_property_edit_interaction(self):
        self._callback()


class _Notice:
    def __init__(self, changed_paths=(), resynced_paths=()):
        self._changed_paths = list(changed_paths)
        self._resynced_paths = list(resynced_paths)

    def GetChangedInfoOnlyPaths(self):  # noqa: N802 - mimic USD API
        return self._changed_paths

    def GetResyncedPaths(self):  # noqa: N802 - mimic USD API
        return self._resynced_paths


class TestUsdAttributeValueModelEditBatching(omni.kit.test.AsyncTestCase):
    """Regression tests for live batch previews in UsdAttributeValueModel."""

    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()

    async def tearDown(self):
        omni.kit.undo.clear_stack()
        if self.context:
            await self.context.close_stage_async()
        self.context = None
        self.stage = None

    async def test_begin_edit_does_not_start_drag_batching(self):
        # Arrange
        model = _make_model(self.stage)

        # Act
        model.begin_edit()

        # Assert
        self.assertFalse(model.is_batch_editing)

    async def test_set_value_during_batch_previews_latest_value_on_next_update(self):
        """Preview coalesced input before release without recording undo."""
        # Arrange
        model = _make_model(self.stage)
        omni.kit.undo.clear_stack()
        model.begin_batch_edit()

        try:
            # Act
            model.set_value(5.0)
            first_task = model._pending_preview_task
            model.set_value(8.0)
            second_task = model._pending_preview_task
            cached_value = model.get_value_as_float()
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()

            # Assert
            self.assertIsNotNone(first_task)
            self.assertIs(second_task, first_task)
            self.assertAlmostEqual(cached_value, 8.0)
            self.assertAlmostEqual(_usd_value(self.stage), 8.0)
            self.assertAlmostEqual(model.get_value_as_float(), 8.0)
            self.assertEqual(list(omni.kit.undo.get_undo_stack()), [])
        finally:
            model.cancel_property_edit_interaction()

    async def test_set_value_outside_batch_edit_writes_immediately(self):
        # Arrange
        model = _make_model(self.stage, value=0.0)

        # Act
        model.set_value(42.0)

        # Assert
        self.assertAlmostEqual(_usd_value(self.stage), 42.0)

    async def test_set_value_outside_batch_edit_defers_usd_notices_for_write_scope(self):
        # Arrange
        model = _make_model(self.stage, value=0.0)
        scope = MagicMock()

        with patch(
            "omni.flux.property_widget_builder.model.usd.item_model.attr_value._defer_usd_notices",
            return_value=scope,
        ) as defer_notices:
            # Act
            model.set_value(42.0)

        # Assert
        defer_notices.assert_called_once_with(self.stage)
        scope.__enter__.assert_called_once_with()
        scope.__exit__.assert_called_once()
        self.assertAlmostEqual(_usd_value(self.stage), 42.0)

    async def test_cancel_property_edit_interaction_restores_cached_value_from_usd(self):
        # Arrange
        model = _make_model(self.stage, value=5.0)
        model._set_internal_value(9.0)
        model._has_wrong_value = True

        # Act
        model.cancel_property_edit_interaction()

        # Assert
        self.assertAlmostEqual(model.get_value_as_float(), 5.0)
        self.assertFalse(model._has_wrong_value)

    async def test_set_value_during_batch_edit_updates_only_cached_value(self):
        # Arrange
        model = _make_model(self.stage, value=0.0)
        try:
            with patch("omni.kit.undo.begin_group"), patch("omni.kit.undo.end_group"):
                model.begin_batch_edit()

                # Act
                model.set_value(5.0)

                # Assert
                self.assertAlmostEqual(model.get_value_as_float(), 5.0)
                self.assertAlmostEqual(_usd_value(self.stage), 0.0)
        finally:
            model.cancel_property_edit_interaction()

    async def test_cancel_property_edit_interaction_aborts_active_batch_edit(self):
        # Arrange
        model = _make_model(self.stage, value=0.0)

        with patch("omni.kit.undo.begin_group"), patch("omni.kit.undo.end_group") as end_group:
            model.begin_batch_edit()
            model.set_value(7.0)

            # Act
            model.cancel_property_edit_interaction()

            # Assert
            end_group.assert_not_called()
            self.assertFalse(model.is_batch_editing)
            self.assertAlmostEqual(model.get_value_as_float(), 0.0)
            self.assertAlmostEqual(_usd_value(self.stage), 0.0)

    async def test_cancel_property_edit_interaction_runs_parent_cancel_callback_after_local_error(self):
        # Arrange
        model = _make_model(self.stage, value=0.0)
        cancel_calls = []
        model.subscribe_property_edit_cancel_fn(lambda: cancel_calls.append(model))
        model._is_batch_editing = True
        model._set_internal_value(9.0)
        model._has_wrong_value = True

        with patch.object(model, "_cancel_batch_edit", side_effect=RuntimeError("cancel failed")):
            # Act
            with self.assertRaisesRegex(RuntimeError, "cancel failed"):
                model.cancel_property_edit_interaction()

        # Assert
        self.assertEqual(cancel_calls, [model])
        self.assertEqual(model.get_value_as_string(), "0.0")
        self.assertFalse(model._has_wrong_value)

    async def test_end_edit_runs_parent_end_callback_after_batch_flush_error(self):
        # Arrange
        model = _make_model(self.stage, value=0.0)
        end_calls = []
        model.set_property_edit_callbacks(None, end_calls.append)
        model._is_batch_editing = True
        model._set_internal_value(9.0)
        model._has_wrong_value = True

        with patch.object(model, "end_batch_edit", side_effect=RuntimeError("flush failed")):
            # Act
            with self.assertRaisesRegex(RuntimeError, "flush failed"):
                model.end_edit()

        # Assert
        self.assertEqual(end_calls, [model])
        self.assertEqual(model.get_value_as_string(), "0.0")
        self.assertFalse(model._has_wrong_value)

    async def test_failed_usd_write_restores_cached_value(self):
        # Arrange
        model = _make_model(self.stage, value=0.0)

        with patch.object(model, "_set_attribute_value", side_effect=RuntimeError("write failed")):
            # Act
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                model.set_value(7.0)

        # Assert
        self.assertAlmostEqual(model.get_value_as_float(), 0.0)
        self.assertAlmostEqual(_usd_value(self.stage), 0.0)

    async def test_group_edit_copy_when_first_target_command_fails_stops_and_remains_unlinked(self):
        # Arrange
        original_values = ((1.0, 2.0, 3.0), (9.0, 8.0, 7.0))
        item, attributes = _make_group_edit_item(self.stage, original_values)

        try:
            with patch("omni.kit.commands.execute", return_value=(False, None)) as execute_command:
                # Act
                item.toggle_linked_edit()

            # Assert
            self.assertFalse(item.linked_edit_enabled)
            self.assertEqual(execute_command.call_count, 1)
            self.assertEqual([attr.Get() for attr in attributes], [Gf.Vec3f(*value) for value in original_values])
            self.assertEqual(
                [model._values for model in item.value_models],
                [[Gf.Vec3f(*value) for value in original_values]] * 3,
            )
        finally:
            item.destroy()

    async def test_group_edit_copy_when_later_target_command_fails_rolls_back_and_remains_unlinked(self):
        # Arrange
        original_values = ((1.0, 2.0, 3.0), (9.0, 8.0, 7.0))
        item, attributes = _make_group_edit_item(self.stage, original_values)
        omni.kit.undo.clear_stack()
        omni.kit.undo.clear_history()
        sentinel_prim = self.stage.DefinePrim("/FailedCopyUndoSentinel")
        sentinel_attr = sentinel_prim.CreateAttribute("value", Sdf.ValueTypeNames.Float)
        sentinel_attr.Set(1.0)
        omni.kit.commands.execute(
            "ChangeProperty",
            prop_path=str(sentinel_attr.GetPath()),
            value=2.0,
            prev=None,
            usd_context_name="",
        )
        execute = omni.kit.commands.execute
        change_property_calls = 0

        def fail_second_change_property(command_name, **kwargs):
            nonlocal change_property_calls
            if command_name == "ChangeProperty":
                change_property_calls += 1
                if change_property_calls == 2:
                    return False, None
            return execute(command_name, **kwargs)

        try:
            with patch("omni.kit.commands.execute", side_effect=fail_second_change_property):
                # Act
                item.toggle_linked_edit()

            # Assert
            self.assertFalse(item.linked_edit_enabled)
            self.assertEqual(change_property_calls, 2)
            self.assertEqual([attr.Get() for attr in attributes], [Gf.Vec3f(*value) for value in original_values])
            self.assertEqual(
                [model._values for model in item.value_models],
                [[Gf.Vec3f(*value) for value in original_values]] * 3,
            )
            self.assertFalse(omni.kit.undo.can_redo())
            self.assertEqual(
                [entry.name for entry in omni.kit.undo.get_undo_stack() if entry.level == 0],
                ["ChangeProperty"],
            )
        finally:
            item.destroy()
            omni.kit.undo.clear_stack()
            omni.kit.undo.clear_history()

    async def test_group_edit_copy_when_related_spec_succeeds_and_value_fails_restores_override_and_cache(self):
        # Arrange
        item, scale_attr, target_layer, related_path = _make_group_edit_item_with_related_override(self.stage)
        execute = omni.kit.commands.execute
        change_property_calls = 0

        def fail_value_write(command_name, **kwargs):
            nonlocal change_property_calls
            if command_name == "ChangeProperty":
                change_property_calls += 1
                if change_property_calls == 2:
                    return False, None
            return execute(command_name, **kwargs)

        try:
            with patch("omni.kit.commands.execute", side_effect=fail_value_write):
                # Act
                item.toggle_linked_edit()

            # Assert
            self.assertFalse(item.linked_edit_enabled)
            self.assertEqual(scale_attr.Get(), Gf.Vec3f(1.0, 2.0, 3.0))
            self.assertIsNone(target_layer.GetPropertyAtPath(related_path))
            self.assertEqual([model.get_value_as_float() for model in item.value_models], [1.0, 2.0, 3.0])
        finally:
            item.destroy()

    async def test_group_edit_copy_when_python_error_follows_write_rolls_back_and_reraises(self):
        # Arrange
        original_values = ((1.0, 2.0, 3.0), (9.0, 8.0, 7.0))
        item, attributes = _make_group_edit_item(self.stage, original_values)
        x_model = item.value_models[0]
        get_target_layer = x_model._get_target_layer
        x_model._get_target_layer = MagicMock(
            side_effect=[get_target_layer(attributes[0]), RuntimeError("lookup failed")]
        )
        for model in item.value_models:
            model._value = Gf.Vec3f(99.0)

        try:
            # Act
            with self.assertRaisesRegex(RuntimeError, "lookup failed"):
                item.toggle_linked_edit()

            # Assert
            self.assertFalse(item.linked_edit_enabled)
            self.assertEqual([attr.Get() for attr in attributes], [Gf.Vec3f(*value) for value in original_values])
            self.assertEqual([model.get_value_as_float() for model in item.value_models], [9.0, 8.0, 7.0])
        finally:
            item.destroy()

    async def test_group_edit_copy_inside_outer_undo_group_raises_before_writing(self):
        # Arrange
        item, attributes = _make_group_edit_item(self.stage, ((1.0, 2.0, 3.0),))

        try:
            with omni.kit.undo.group():
                # Act
                with self.assertRaisesRegex(RuntimeError, "top-level undo operation"):
                    item.value_models[0].copy_first_channel_to_all_attributes()

            # Assert
            self.assertEqual(attributes[0].Get(), Gf.Vec3f(1.0, 2.0, 3.0))
        finally:
            item.destroy()
            omni.kit.undo.clear_stack()
            omni.kit.undo.clear_history()

    async def test_group_edit_value_when_later_target_fails_rolls_back_and_refreshes_linked_caches(self):
        # Arrange
        original_values = ((1.0, 2.0, 3.0), (9.0, 8.0, 7.0))
        item, attributes = _make_group_edit_item(self.stage, original_values)

        try:
            item.set_linked_edit_enabled(True)
            x_model = item.value_models[0]
            execute = omni.kit.commands.execute
            change_property_calls = 0

            def fail_second_change_property(command_name, **kwargs):
                nonlocal change_property_calls
                if command_name == "ChangeProperty":
                    change_property_calls += 1
                    if change_property_calls == 2:
                        return False, None
                return execute(command_name, **kwargs)

            with patch("omni.kit.commands.execute", side_effect=fail_second_change_property):
                # Act
                x_model.set_value(42.0)

            # Assert
            expected_values = [Gf.Vec3f(*value) for value in original_values]
            self.assertEqual([attr.Get() for attr in attributes], expected_values)
            self.assertEqual([model._values for model in item.value_models], [expected_values] * 3)
            self.assertEqual([model.get_value_as_float() for model in item.value_models], [9.0, 8.0, 7.0])
        finally:
            item.destroy()
            omni.kit.undo.clear_stack()
            omni.kit.undo.clear_history()

    async def test_group_edit_batch_when_later_target_fails_rolls_back_and_refreshes_linked_caches(self):
        """Failed preview or release commands restore every target and linked channel cache."""
        execute = omni.kit.commands.execute
        for phase in ("preview", "release"):
            with self.subTest(phase=phase):
                # Arrange
                original_values = ((1.0, 2.0, 3.0), (9.0, 8.0, 7.0))
                item, attributes = _make_group_edit_item(self.stage, original_values)

                try:
                    item.set_linked_edit_enabled(True)
                    x_model = item.value_models[0]
                    omni.kit.undo.clear_stack()
                    omni.kit.undo.clear_history()
                    x_model.begin_batch_edit()
                    x_model.set_value(42.0)
                    change_property_calls = 0

                    def fail_second_change_property(command_name, **kwargs):
                        nonlocal change_property_calls
                        if command_name == "ChangeProperty":
                            change_property_calls += 1
                            if change_property_calls == 2:
                                return False, None
                        return execute(command_name, **kwargs)

                    with patch("omni.kit.commands.execute", side_effect=fail_second_change_property):
                        # Act
                        if phase == "preview":
                            await omni.kit.app.get_app().next_update_async()
                            await omni.kit.app.get_app().next_update_async()
                        else:
                            x_model.end_batch_edit()

                    # Assert
                    self.assertEqual(change_property_calls, 2)
                    self.assertFalse(x_model.is_batch_editing)
                    self.assertIsNone(x_model._pending_preview_task)
                    self.assertFalse(omni.kit.undo.can_undo())
                    expected_values = [Gf.Vec3f(*value) for value in original_values]
                    self.assertEqual([attr.Get() for attr in attributes], expected_values)
                    self.assertEqual([model._values for model in item.value_models], [expected_values] * 3)
                    self.assertEqual([model.get_value_as_float() for model in item.value_models], [9.0, 8.0, 7.0])
                finally:
                    item.destroy()
                    for attr in attributes:
                        self.stage.RemovePrim(attr.GetPath().GetPrimPath())
                    omni.kit.undo.clear_stack()
                    omni.kit.undo.clear_history()

    async def test_reset_row_nested_failed_write_closes_group_without_consuming_prior_history(self):
        # Arrange
        item, _attributes = _make_group_edit_item(self.stage, ((2.0, 3.0, 4.0), (5.0, 6.0, 7.0)))

        try:
            omni.kit.undo.clear_stack()
            omni.kit.undo.clear_history()
            sentinel_prim = self.stage.DefinePrim("/NestedResetUndoSentinel")
            sentinel_attr = sentinel_prim.CreateAttribute("value", Sdf.ValueTypeNames.Float)
            sentinel_attr.Set(1.0)
            omni.kit.commands.execute(
                "ChangeProperty",
                prop_path=str(sentinel_attr.GetPath()),
                value=2.0,
                prev=None,
                usd_context_name="",
            )
            execute = omni.kit.commands.execute
            change_property_calls = 0

            def fail_second_change_property(command_name, **kwargs):
                nonlocal change_property_calls
                if command_name == "ChangeProperty":
                    change_property_calls += 1
                    if change_property_calls == 2:
                        return False, None
                return execute(command_name, **kwargs)

            with patch("omni.kit.commands.execute", side_effect=fail_second_change_property):
                # Act
                item.reset_row_value()

            # Assert
            self.assertEqual(sentinel_attr.Get(), 2.0)
            self.assertEqual(
                [entry.name for entry in omni.kit.undo.get_undo_stack() if entry.level == 0],
                ["ChangeProperty", "Group"],
            )
        finally:
            item.destroy()
            omni.kit.undo.clear_stack()
            omni.kit.undo.clear_history()

    async def test_group_edit_copy_when_values_are_uniform_does_not_consume_next_undo(self):
        # Arrange
        item, _attributes = _make_group_edit_item(self.stage, ((1.0, 1.0, 1.0),))

        try:
            omni.kit.undo.clear_stack()
            omni.kit.undo.clear_history()
            prim = self.stage.DefinePrim("/UndoSentinel")
            attr = prim.CreateAttribute("sentinel", Sdf.ValueTypeNames.Float)
            attr.Set(1.0)
            omni.kit.commands.execute(
                "ChangeProperty",
                prop_path=str(attr.GetPath()),
                value=2.0,
                prev=None,
                usd_context_name="",
            )
            item.toggle_linked_edit()

            # Act
            omni.kit.undo.undo()

            # Assert
            self.assertTrue(item.linked_edit_enabled)
            self.assertEqual(attr.Get(), 1.0)
        finally:
            item.destroy()
            omni.kit.undo.clear_stack()
            omni.kit.undo.clear_history()

    async def test_preview_multiple_frames_reserves_each_property_once(self):
        """Each selected property captures its original spec once across preview frames."""
        # Arrange
        attributes = []
        originals = [float(index) for index in range(32)]
        for index, original in enumerate(originals):
            attribute = self.stage.DefinePrim(f"/Reservation{index}").CreateAttribute("value", Sdf.ValueTypeNames.Float)
            attribute.Set(original)
            attributes.append(attribute)
        sdk_undo = attr_value.UsdLayerUndo
        reservations = []

        def create_reservation(layer):
            """Observe SDK calls while preserving real spec capture and restoration."""
            reservation = Mock(wraps=sdk_undo(layer))
            reservations.append(reservation)
            return reservation

        model = UsdAttributeValueModel("", [attribute.GetPath() for attribute in attributes], 0)
        try:
            with patch.object(attr_value, "UsdLayerUndo", side_effect=create_reservation):
                # Act
                model.begin_batch_edit()
                model.set_value(100.0)
                await omni.kit.app.get_app().next_update_async()
                await omni.kit.app.get_app().next_update_async()
                first_reservation_count = len(reservations)
                first_preview_values = [attribute.Get() for attribute in attributes]
                model.set_value(200.0)
                await omni.kit.app.get_app().next_update_async()
                await omni.kit.app.get_app().next_update_async()
                second_preview_values = [attribute.Get() for attribute in attributes]
                model.cancel_property_edit_interaction()

            # Assert
            self.assertEqual(first_preview_values, [100.0] * len(attributes))
            self.assertEqual(second_preview_values, [200.0] * len(attributes))
            self.assertEqual(first_reservation_count, len(attributes))
            self.assertEqual(len(reservations), first_reservation_count)
            for reservation in reservations:
                self.assertEqual(reservation.reserve.call_count, 1)
            self.assertEqual([attribute.Get() for attribute in attributes], originals)
            self.assertEqual(list(omni.kit.undo.get_undo_stack()), [])
        finally:
            model.cancel_property_edit_interaction()

    async def test_release_with_pending_preview_keeps_exact_final_value(self):
        """A pending preview cannot overwrite the released value."""
        # Arrange
        model = _make_model(self.stage, value=3.0)
        try:
            model.begin_batch_edit()
            model.set_value(7.0)
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            model.set_value(11.0)

            # Act
            model.end_batch_edit()
            released_value = _usd_value(self.stage)
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()

            # Assert
            self.assertAlmostEqual(released_value, 11.0)
            self.assertAlmostEqual(_usd_value(self.stage), 11.0)
            self.assertIsNone(model._pending_preview_task)
            self.assertFalse(model.is_batch_editing)
        finally:
            model.cancel_property_edit_interaction()

    async def test_batch_cancel_or_noop_preserves_existing_redo(self):
        """Cancelled and unchanged drags preserve an unrelated redo entry."""
        for finish in ("cancel", "return", "unchanged"):
            with self.subTest(finish=finish):
                # Arrange
                omni.kit.undo.clear_stack()
                model = _make_model(self.stage, value=0.0)
                try:
                    model.set_value(4.0)
                    omni.kit.undo.undo()
                    model.refresh()
                    model.begin_batch_edit()
                    if finish != "unchanged":
                        model.set_value(8.0)
                        await omni.kit.app.get_app().next_update_async()
                        await omni.kit.app.get_app().next_update_async()
                    if finish == "return":
                        model.set_value(0.0)
                    redo_available_during_preview = omni.kit.undo.can_redo()

                    # Act
                    if finish == "cancel":
                        model.cancel_property_edit_interaction()
                    else:
                        model.end_batch_edit()
                    restored_value = _usd_value(self.stage)
                    empty_undo = not omni.kit.undo.can_undo()
                    omni.kit.undo.redo()

                    # Assert
                    self.assertAlmostEqual(restored_value, 0.0)
                    self.assertTrue(redo_available_during_preview)
                    self.assertTrue(empty_undo)
                    self.assertAlmostEqual(_usd_value(self.stage), 4.0)
                    self.assertIsNone(model._pending_preview_task)
                finally:
                    model.cancel_property_edit_interaction()

    async def test_release_displayed_original_commits_other_mixed_target(self):
        """Returning to the displayed value still updates differing selected values."""
        # Arrange
        omni.kit.undo.clear_stack()
        _make_model(self.stage, value=2.0)
        first_attr = self.stage.GetAttributeAtPath("/DragTestPrim.testFloat")
        second_attr = self.stage.DefinePrim("/OtherPrim").CreateAttribute("testFloat", Sdf.ValueTypeNames.Float)
        second_attr.Set(6.0)
        model = UsdAttributeValueModel("", [first_attr.GetPath(), second_attr.GetPath()], 0)
        try:
            model.begin_batch_edit()
            model.set_value(10.0)
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            model.set_value(6.0)

            # Act
            model.end_batch_edit()
            committed = (first_attr.Get(), second_attr.Get())
            undo_count = sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack())
            omni.kit.undo.undo()

            # Assert
            self.assertEqual(committed, (6.0, 6.0))
            self.assertEqual(undo_count, 1)
            self.assertEqual((first_attr.Get(), second_attr.Get()), (2.0, 6.0))
        finally:
            model.cancel_property_edit_interaction()

    async def test_preview_exception_restores_original_and_clears_batch(self):
        """A failed later preview reports its error and rolls back earlier previews."""
        # Arrange
        model = _make_model(self.stage, value=3.0)
        try:
            model.begin_batch_edit()
            model.set_value(7.0)
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            preview_value = _usd_value(self.stage)

            with (
                patch.object(model, "_set_attribute_value", side_effect=RuntimeError("preview failed")),
                patch.object(attr_value.carb, "log_error") as log_error,
            ):
                # Act
                model.set_value(9.0)
                await omni.kit.app.get_app().next_update_async()
                await omni.kit.app.get_app().next_update_async()

                # Assert
                self.assertAlmostEqual(preview_value, 7.0)
                self.assertAlmostEqual(_usd_value(self.stage), 3.0)
                self.assertAlmostEqual(model.get_value_as_float(), 3.0)
                self.assertIsNone(model._pending_preview_task)
                self.assertFalse(model.is_batch_editing)
                log_error.assert_called_once()
                error_message = log_error.call_args.args[0]
                self.assertIn("Failed to preview property edit", error_message)
                self.assertIn("Traceback (most recent call last):", error_message)
                self.assertIn("RuntimeError: preview failed", error_message)
        finally:
            model.cancel_property_edit_interaction()

    async def test_preview_reservation_failure_rolls_back_earlier_writes_without_publishing_capture(self):
        """A failed capture leaves no reservation and restores earlier preview writes."""
        # Arrange
        attributes = []
        for index in range(2):
            attribute = self.stage.DefinePrim(f"/CaptureFailure{index}").CreateAttribute(
                "value", Sdf.ValueTypeNames.Float
            )
            attribute.Set(3.0)
            attributes.append(attribute)
        model = UsdAttributeValueModel("", [attribute.GetPath() for attribute in attributes], 0)
        try:
            sdk_undo = attr_value.UsdLayerUndo
            failed_key = (self.stage.GetRootLayer().identifier, attributes[1].GetPath())
            failed_capture_state = []

            def create_reservation(layer):
                """Inject capture failure only into reservations owned by the value model."""
                reservation = sdk_undo(layer)

                def reserve_property(property_path):
                    """Fail the second capture after the first property's preview was written."""
                    if property_path == attributes[1].GetPath():
                        failed_capture_state.append(
                            (failed_key in model._preview_layer_undos, [attribute.Get() for attribute in attributes])
                        )
                        raise RuntimeError("reservation failed")
                    reservation.reserve(property_path)

                reservation_spy = Mock(wraps=reservation)
                reservation_spy.reserve.side_effect = reserve_property
                return reservation_spy

            with (
                patch.object(attr_value, "UsdLayerUndo", side_effect=create_reservation),
                patch.object(attr_value.carb, "log_error") as log_error,
            ):
                # Act
                model.begin_batch_edit()
                model.set_value(7.0)
                await omni.kit.app.get_app().next_update_async()
                await omni.kit.app.get_app().next_update_async()

                # Assert
                self.assertEqual(failed_capture_state, [(False, [7.0, 3.0])])
                self.assertEqual([attribute.Get() for attribute in attributes], [3.0, 3.0])
                self.assertAlmostEqual(model.get_value_as_float(), 3.0)
                self.assertEqual(model._preview_layer_undos, {})
                self.assertIsNone(model._pending_preview_task)
                self.assertFalse(model.is_batch_editing)
                self.assertEqual(list(omni.kit.undo.get_undo_stack()), [])
                log_error.assert_called_once()
                self.assertIn("RuntimeError: reservation failed", log_error.call_args.args[0])
        finally:
            model.cancel_property_edit_interaction()

    async def test_cancelled_preview_does_not_clear_new_gesture_task(self):
        """An older task's finalizer cannot discard the next gesture's preview."""
        # Arrange
        model = _make_model(self.stage, value=3.0)
        try:
            entered = asyncio.Event()
            resume = asyncio.Event()

            async def wait_for_preview():
                entered.set()
                await resume.wait()

            with patch.object(attr_value, "get_app") as get_app:
                get_app.return_value.next_update_async = wait_for_preview
                model.begin_batch_edit()
                model.set_value(7.0)
                await entered.wait()
                old_task = model._pending_preview_task

                # Act
                model.cancel_property_edit_interaction()
                model.begin_batch_edit()
                model.set_value(9.0)
                new_task = model._pending_preview_task
                await asyncio.gather(old_task, return_exceptions=True)
                retained_task = model._pending_preview_task
                resume.set()
                await new_task

                # Assert
                self.assertTrue(old_task.cancelled())
                self.assertIs(retained_task, new_task)
                self.assertAlmostEqual(_usd_value(self.stage), 9.0)
        finally:
            model.cancel_property_edit_interaction()

    async def test_cancel_preview_removes_related_overrides_and_restores_metadata(self):
        """Rollback removes preview-only overrides without damaging weaker specs."""
        # Arrange
        _make_model(self.stage, value=3.0)
        attr = self.stage.GetAttributeAtPath("/DragTestPrim.testFloat")
        attr.SetCustomDataByKey("test", "preserve")
        attr.Set(4.0, 1.0)
        related = attr.GetPrim().CreateAttribute("related", Sdf.ValueTypeNames.Float)
        related.Set(9.0)
        original_layer = self.stage.GetRootLayer().ExportToString()
        edit_layer = self.stage.GetSessionLayer()
        self.stage.SetEditTarget(edit_layer)
        model = UsdAttributeValueModel("", [attr.GetPath()], 0, related_override_paths=[related.GetPath()])
        try:
            model.begin_batch_edit()
            model.set_value(7.0)
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            preview_spec = edit_layer.GetPropertyAtPath(attr.GetPath()) is not None
            related_spec = edit_layer.GetPropertyAtPath(related.GetPath()) is not None

            # Act
            model.cancel_property_edit_interaction()

            # Assert
            self.assertTrue(preview_spec)
            self.assertTrue(related_spec)
            self.assertIsNone(edit_layer.GetPropertyAtPath(attr.GetPath()))
            self.assertIsNone(edit_layer.GetPropertyAtPath(related.GetPath()))
            self.assertEqual(self.stage.GetRootLayer().ExportToString(), original_layer)
            self.assertAlmostEqual(model.get_value_as_float(), 3.0)
        finally:
            model.cancel_property_edit_interaction()

    async def test_cancel_nonpersistent_preview_restores_session_property(self):
        """Reserve the command's session target for nonpersistent attributes."""
        # Arrange
        model = _make_model(self.stage, value=3.0)
        try:
            attr = self.stage.GetAttributeAtPath("/DragTestPrim.testFloat")
            attr.SetCustomDataByKey("nonpersistant", True)
            model.begin_batch_edit()
            model.set_value(7.0)
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            preview_value = attr.Get()

            # Act
            model.cancel_property_edit_interaction()

            # Assert
            self.assertAlmostEqual(preview_value, 7.0)
            self.assertAlmostEqual(attr.Get(), 3.0)
            self.assertIsNone(self.stage.GetSessionLayer().GetPropertyAtPath(attr.GetPath()))
        finally:
            model.cancel_property_edit_interaction()

    async def test_restore_preview_layer_failure_preserves_reservation_and_restores_other_layers(self):
        """A failed property does not prevent restoration in the same or another layer."""
        # Arrange
        attributes = []
        for index in range(3):
            attribute = self.stage.DefinePrim(f"/Rollback{index}").CreateAttribute("value", Sdf.ValueTypeNames.Float)
            attribute.Set(3.0)
            attributes.append(attribute)
        attributes[2].SetCustomDataByKey("nonpersistant", True)
        model = UsdAttributeValueModel("", [attribute.GetPath() for attribute in attributes], 0)
        try:
            model.begin_batch_edit()
            model.set_value(7.0)
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            root_identifier = self.stage.GetRootLayer().identifier
            failed_key = (root_identifier, attributes[0].GetPath())
            failed_reservation = model._preview_layer_undos[failed_key]
            root_reservation = model._preview_layer_undos[(root_identifier, attributes[1].GetPath())]
            session_reservation = model._preview_layer_undos[
                (self.stage.GetSessionLayer().identifier, attributes[2].GetPath())
            ]
            failure = RuntimeError("layer restoration failed")
            model._ignore_refresh = True

            with (
                patch.object(failed_reservation, "undo", side_effect=failure) as failed_undo,
                patch.object(root_reservation, "undo", wraps=root_reservation.undo) as root_undo,
                patch.object(session_reservation, "undo", wraps=session_reservation.undo) as session_undo,
                patch.object(attr_value.carb, "log_error") as log_error,
            ):
                # Act
                with self.assertRaises(RuntimeError) as raised:
                    model.cancel_property_edit_interaction()

                # Assert
                self.assertIs(raised.exception, failure)
                failed_undo.assert_called_once_with()
                root_undo.assert_called_once_with()
                session_undo.assert_called_once_with()
                self.assertEqual(model._preview_layer_undos, {failed_key: failed_reservation})
                self.assertEqual([attribute.Get() for attribute in attributes], [7.0, 3.0, 3.0])
                self.assertIsNone(self.stage.GetSessionLayer().GetPropertyAtPath(attributes[2].GetPath()))
                self.assertTrue(model._ignore_refresh)
                self.assertFalse(model.is_batch_editing)
                self.assertIsNone(model._pending_preview_task)
                log_error.assert_called_once()
                error_message = log_error.call_args.args[0]
                self.assertIn(f"Failed to restore property preview in layer {root_identifier}", error_message)
                self.assertIn(str(attributes[0].GetPath()), error_message)
                self.assertIn("Traceback (most recent call last):", error_message)
                self.assertIn("RuntimeError: layer restoration failed", error_message)
            model._ignore_refresh = False
            model.cancel_property_edit_interaction()
            self.assertEqual([attribute.Get() for attribute in attributes], [3.0, 3.0, 3.0])
            self.assertEqual(model._preview_layer_undos, {})
        finally:
            model._ignore_refresh = False
            model.cancel_property_edit_interaction()

    async def test_cancel_preview_after_failed_restoration_retries_and_preserves_redo(self):
        """Explicit cancellation retries retained reservations after batch mode has ended."""
        for operation in ("release", "cancel"):
            with self.subTest(title=operation):
                # Arrange
                omni.kit.undo.clear_stack()
                model = _make_model(self.stage, value=3.0)
                try:
                    model.set_value(4.0)
                    omni.kit.undo.undo()
                    redo_stack = list(omni.kit.undo.get_redo_stack())
                    model.begin_batch_edit()
                    model.set_value(7.0)
                    await omni.kit.app.get_app().next_update_async()
                    await omni.kit.app.get_app().next_update_async()
                    reservation = next(iter(model._preview_layer_undos.values()))
                    with (
                        patch.object(reservation, "undo", side_effect=RuntimeError("restore failed")),
                        patch.object(attr_value.carb, "log_error"),
                        self.assertRaisesRegex(RuntimeError, "restore failed"),
                    ):
                        if operation == "release":
                            model.end_batch_edit()
                        else:
                            model.cancel_property_edit_interaction()

                    # Act
                    model.cancel_property_edit_interaction()

                    # Assert
                    self.assertAlmostEqual(_usd_value(self.stage), 3.0)
                    self.assertAlmostEqual(model.get_value_as_float(), 3.0)
                    self.assertEqual(model._preview_layer_undos, {})
                    self.assertFalse(model.is_batch_editing)
                    self.assertIsNone(model._pending_preview_task)
                    self.assertFalse(omni.kit.undo.can_undo())
                    self.assertEqual(list(omni.kit.undo.get_redo_stack()), redo_stack)
                finally:
                    model.cancel_property_edit_interaction()

    async def test_edit_with_unresolved_preview_rollback_rejects_without_mutation(self):
        """Unresolved reservations block each edit entry point until explicit cancellation."""
        for operation in ("begin", "typed", "copy", "release"):
            with self.subTest(title=operation):
                # Arrange
                self.stage.RemovePrim("/GroupEditPrim0")
                item, attributes = _make_group_edit_item(self.stage, [(1.0, 2.0, 3.0)])
                try:
                    model = item.value_models[0]
                    model.begin_batch_edit()
                    model.set_value(7.0)
                    await omni.kit.app.get_app().next_update_async()
                    await omni.kit.app.get_app().next_update_async()
                    reservation = next(iter(model._preview_layer_undos.values()))
                    with (
                        patch.object(reservation, "undo", side_effect=RuntimeError("restore failed")),
                        patch.object(attr_value.carb, "log_error"),
                        self.assertRaisesRegex(RuntimeError, "restore failed"),
                    ):
                        model.cancel_property_edit_interaction()
                    cached_values = [tuple(value_model._value) for value_model in item.value_models]
                    authored_value = attributes[0].Get()
                    reservations = dict(model._preview_layer_undos)
                    operations = {
                        "begin": model.begin_batch_edit,
                        "typed": lambda model=model: model._set_value(9.0),
                        "copy": model.copy_first_channel_to_all_attributes,
                        "release": model.end_batch_edit,
                    }

                    with (
                        patch.object(model, "_write_value_to_usd") as write,
                        patch.object(reservation, "undo") as restore,
                        patch.object(omni.kit.undo, "group") as group,
                    ):
                        # Act
                        with self.assertRaisesRegex(RuntimeError, "Property preview rollback is incomplete"):
                            operations[operation]()

                        # Assert
                        write.assert_not_called()
                        restore.assert_not_called()
                        group.assert_not_called()
                        self.assertEqual(
                            [tuple(value_model._value) for value_model in item.value_models], cached_values
                        )
                        self.assertEqual(attributes[0].Get(), authored_value)
                        self.assertEqual(model._preview_layer_undos, reservations)
                        self.assertFalse(model.is_batch_editing)
                        self.assertIsNone(model._pending_preview_task)
                finally:
                    if item.value_models is not None:
                        try:
                            item.value_models[0].cancel_property_edit_interaction()
                        finally:
                            item.destroy()

    async def test_destroy_item_with_preview_restores_authored_state_and_preserves_redo(self):
        """Item-first destruction cancels pending and already applied previews."""
        for preview_applied in (False, True):
            with self.subTest(title=f"preview_applied={preview_applied}"):
                # Arrange
                omni.kit.undo.clear_stack()
                self.stage.RemovePrim("/GroupEditPrim0")
                item, attributes = _make_group_edit_item(self.stage, [(1.0, 2.0, 3.0)])
                try:
                    model = item.value_models[0]
                    original_value = attributes[0].Get()
                    model.set_value(4.0)
                    omni.kit.undo.undo()
                    redo_stack = list(omni.kit.undo.get_redo_stack())
                    original_layer = self.stage.GetRootLayer().ExportToString()
                    model.begin_batch_edit()
                    model.set_value(7.0)
                    if preview_applied:
                        await omni.kit.app.get_app().next_update_async()
                        await omni.kit.app.get_app().next_update_async()

                    # Act
                    item.destroy()
                    await omni.kit.app.get_app().next_update_async()
                    await omni.kit.app.get_app().next_update_async()

                    # Assert
                    self.assertEqual(attributes[0].Get(), original_value)
                    self.assertEqual(self.stage.GetRootLayer().ExportToString(), original_layer)
                    self.assertIsNone(item.value_models)
                    self.assertFalse(model.is_batch_editing)
                    self.assertIsNone(model._pending_preview_task)
                    self.assertEqual(model._preview_layer_undos, {})
                    self.assertFalse(omni.kit.undo.can_undo())
                    self.assertEqual(list(omni.kit.undo.get_redo_stack()), redo_stack)
                finally:
                    if item.value_models is not None:
                        try:
                            item.value_models[0].cancel_property_edit_interaction()
                        finally:
                            item.destroy()

    async def test_destroy_item_after_failed_restoration_keeps_models_available_for_retry(self):
        """A failed item teardown retains its models until explicit destruction succeeds."""
        # Arrange
        item, attributes = _make_group_edit_item(self.stage, [(1.0, 2.0, 3.0)])
        try:
            value_models = item.value_models
            model = value_models[0]
            original_value = attributes[0].Get()
            model.begin_batch_edit()
            model.set_value(7.0)
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            reservation = next(iter(model._preview_layer_undos.values()))
            with (
                patch.object(reservation, "undo", side_effect=RuntimeError("restore failed")),
                patch.object(attr_value.carb, "log_error"),
                self.assertRaisesRegex(RuntimeError, "restore failed"),
            ):
                item.destroy()
            retained_models = item.value_models
            retained_reservations = dict(model._preview_layer_undos)

            # Act
            item.destroy()

            # Assert
            self.assertIs(retained_models, value_models)
            self.assertIn(reservation, retained_reservations.values())
            self.assertIsNone(item.value_models)
            self.assertEqual(attributes[0].Get(), original_value)
            self.assertEqual(model._preview_layer_undos, {})
            self.assertIsNone(model._pending_preview_task)
        finally:
            if item.value_models is not None:
                try:
                    item.value_models[0].cancel_property_edit_interaction()
                finally:
                    item.destroy()

    async def test_destroy_value_model_after_cancellation_is_idempotent(self):
        """Repeated value-model destruction performs no writes or undo operations."""
        # Arrange
        model = _make_model(self.stage, value=3.0)
        model.destroy()
        with (
            patch.object(model, "_write_value_to_usd") as write,
            patch.object(omni.kit.undo, "group") as group,
        ):
            # Act
            model.destroy()

            # Assert
            write.assert_not_called()
            group.assert_not_called()
            self.assertAlmostEqual(_usd_value(self.stage), 3.0)
            self.assertIsNone(model._pending_preview_task)
            self.assertEqual(model._preview_layer_undos, {})

    async def test_cancel_mapped_preview_restores_variant_property(self):
        """Rollback uses the mapped spec path inside a local layer's variant."""
        # Arrange
        prim = self.stage.DefinePrim("/Instance")
        variants = prim.GetVariantSets().AddVariantSet("preview")
        variants.AddVariant("selected")
        variants.SetVariantSelection("selected")
        with variants.GetVariantEditContext():
            prim.CreateAttribute("value", Sdf.ValueTypeNames.Float).Set(3.0)
            edit_target = self.stage.GetEditTarget()
        self.stage.SetEditTarget(edit_target)
        layer = self.stage.GetRootLayer()
        before = layer.ExportToString()
        model = UsdAttributeValueModel("", [Sdf.Path("/Instance.value")], 0)
        try:
            model.begin_batch_edit()
            model.set_value(7.0)
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            preview_value = prim.GetAttribute("value").Get()

            # Act
            model.cancel_property_edit_interaction()

            # Assert
            self.assertAlmostEqual(preview_value, 7.0)
            self.assertEqual(layer.ExportToString(), before)
            self.assertAlmostEqual(prim.GetAttribute("value").Get(), 3.0)
        finally:
            model.cancel_property_edit_interaction()


class TestUSDModelInteractiveNotices(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()

    async def tearDown(self):
        if self.context:
            await self.context.close_stage_async()
        self.context = None
        self.stage = None

    @staticmethod
    async def _wait_for_deferred_property_edit_finish(model: USDModel) -> None:
        for _ in range(5):
            if model._pending_property_edit_finish_task is None:
                return
            await omni.kit.app.get_app().next_update_async()

    async def test_interaction_token_stays_open_until_last_active_field_ends(self):
        # Arrange
        model = USDModel(context_name="")
        token = object()
        first_field_model = _TabFieldModel()
        second_field_model = _TabFieldModel()

        with (
            patch.object(_model_module, "_begin_interaction", return_value=token, create=True) as begin_interaction,
            patch.object(_model_module, "_end_interaction", create=True) as end_interaction,
        ):
            # Act
            model._on_item_model_begin_edit(first_field_model)
            model._on_item_model_begin_edit(second_field_model)
            model._item_model_end_edit(first_field_model)

            # Assert
            begin_interaction.assert_called_once_with(model.stage)
            end_interaction.assert_not_called()
            self.assertTrue(model.supress_usd_events_during_widget_edit)

            # Act
            model._item_model_end_edit(second_field_model)

            # Assert
            end_interaction.assert_not_called()
            await self._wait_for_deferred_property_edit_finish(model)
            end_interaction.assert_called_once_with(token)

        self.assertFalse(model.supress_usd_events_during_widget_edit)

    async def test_begin_property_edit_waits_for_available_stage_before_opening_token(self):
        # Arrange
        model = USDModel(context_name="")
        model._context = MagicMock()
        stage = object()
        token = object()
        first_field_model = _TabFieldModel()
        model._context.get_stage.side_effect = [None, stage]

        with (
            patch.object(_model_module, "_begin_interaction", return_value=token, create=True) as begin_interaction,
            patch.object(_model_module, "_end_interaction", create=True) as end_interaction,
        ):
            # Act
            model._on_item_model_begin_edit(first_field_model)
            model._item_model_end_edit(first_field_model)

            # Assert
            begin_interaction.assert_called_once_with(stage)
            end_interaction.assert_not_called()
            await self._wait_for_deferred_property_edit_finish(model)
            end_interaction.assert_called_once_with(token)

        self.assertFalse(model.supress_usd_events_during_widget_edit)

    async def test_destroy_cancels_deferred_property_edit_finish(self):
        # Arrange
        model = USDModel(context_name="")
        field_model = _TabFieldModel()
        model._on_item_model_begin_edit(field_model)
        model._item_model_end_edit(field_model)
        task = model._pending_property_edit_finish_task
        self.assertIsNotNone(task)

        try:
            # Act
            model.destroy()
            await omni.kit.app.get_app().next_update_async()

            # Assert
            self.assertTrue(task.cancelled())
        finally:
            if task is not None and not task.done():
                task.cancel()
                await omni.kit.app.get_app().next_update_async()

    async def test_destroy_active_preview_restores_original_value(self):
        """Destroy cancels child previews before discarding their owning items."""
        # Arrange
        value_model = _make_model(self.stage, value=3.0)
        model = USDModel(context_name="")
        try:
            item = ItemGroup("preview", expanded=True)
            item._value_models = [value_model]
            model.set_items([item])
            value_model.begin_edit()
            value_model.begin_batch_edit()
            value_model.set_value(7.0)
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            preview_value = _usd_value(self.stage)

            # Act
            model.destroy()
            await omni.kit.app.get_app().next_update_async()

            # Assert
            self.assertAlmostEqual(preview_value, 7.0)
            self.assertAlmostEqual(_usd_value(self.stage), 3.0)
            self.assertFalse(value_model.is_batch_editing)
            self.assertIsNone(value_model._pending_preview_task)
        finally:
            model.destroy()

    async def test_cleanup_failed_restoration_retains_nested_items_until_explicit_retry(self):
        """Failed destruction or replacement preserves nested preview recovery state."""
        for operation in ("destroy", "replace"):
            with self.subTest(title=operation):
                # Arrange
                omni.kit.undo.clear_stack()
                model = USDModel(context_name="")
                group = ItemGroup("preview", expanded=True)
                item, attributes = _make_group_edit_item(self.stage, [(1.0, 2.0, 3.0)])
                item.parent = group
                value_model = item.value_models[0]
                try:
                    model.set_items([group])
                    subscriptions = tuple(model._subscriptions)
                    value_model.set_value(4.0)
                    omni.kit.undo.undo()
                    redo_stack = list(omni.kit.undo.get_redo_stack())
                    value_model.begin_edit()
                    value_model.begin_batch_edit()
                    value_model.set_value(7.0)
                    await omni.kit.app.get_app().next_update_async()
                    await omni.kit.app.get_app().next_update_async()
                    reservations = dict(value_model._preview_layer_undos)
                    reservation = next(iter(reservations.values()))
                    value_model.set_value(9.0)
                    failure = RuntimeError("restore failed")
                    cleanup = model.destroy if operation == "destroy" else lambda model=model: model.set_items([])

                    # Act
                    with (
                        patch.object(reservation, "undo", side_effect=failure),
                        patch.object(attr_value.carb, "log_error"),
                        self.assertRaises(RuntimeError) as raised,
                    ):
                        cleanup()
                    retained_item_ids = [id(owned_item) for owned_item in model.get_all_items(include_hidden=True)]
                    retained_child_ids = [id(child) for child in group.children]
                    retained_subscriptions = tuple(model._subscriptions or ())
                    retained_reservations = dict(value_model._preview_layer_undos)
                    pending_task = value_model._pending_preview_task
                    failed_value = attributes[0].Get()
                    cleanup()
                    await omni.kit.app.get_app().next_update_async()

                    # Assert
                    self.assertIs(raised.exception, failure)
                    self.assertEqual(retained_item_ids, [id(group), id(item)])
                    self.assertEqual(retained_child_ids, [id(item)])
                    self.assertEqual(retained_subscriptions, subscriptions)
                    self.assertEqual(retained_reservations, reservations)
                    self.assertIsNone(pending_task)
                    self.assertEqual(failed_value, Gf.Vec3f(7.0, 2.0, 3.0))
                    self.assertEqual(attributes[0].Get(), Gf.Vec3f(1.0, 2.0, 3.0))
                    self.assertEqual(value_model._preview_layer_undos, {})
                    self.assertEqual(model.get_all_items(include_hidden=True), [])
                    self.assertFalse(omni.kit.undo.can_undo())
                    self.assertEqual(list(omni.kit.undo.get_redo_stack()), redo_stack)
                finally:
                    with ExitStack() as cleanup_stack:
                        cleanup_stack.callback(omni.kit.undo.clear_stack)
                        cleanup_stack.callback(self.stage.RemovePrim, "/GroupEditPrim0")
                        cleanup_stack.callback(
                            lambda item=item: item.destroy() if item.value_models is not None else None
                        )
                        cleanup_stack.callback(model.destroy)

                        value_model.set_property_edit_callbacks(None, None)
                        value_model.cancel_property_edit_interaction()

    async def test_cleanup_after_item_destroy_accepts_destroyed_items(self):
        """Support property panes that destroy items before model cleanup or replacement."""
        for operation in ("destroy", "replace"):
            with self.subTest(operation=operation):
                # Arrange
                model = USDModel(context_name="")
                item = ItemGroup("destroyed", expanded=True)
                model.set_items([item])
                item.destroy()
                self.assertIsNone(item.value_models)

                with patch.object(_model_module._Model, "destroy") as parent_destroy:
                    # Act
                    if operation == "destroy":
                        model.destroy()
                    else:
                        model.set_items([])

                    # Assert
                    if operation == "destroy":
                        parent_destroy.assert_called_once_with()
                    else:
                        self.assertEqual(model.get_all_items(), [])

    async def test_unmatched_end_edit_does_not_fire_final_edit_callbacks(self):
        # Arrange
        model = USDModel(context_name="")
        field_model = _TabFieldModel()
        value_changed_callbacks = []
        item_model_end_callbacks = []
        model._value_changed_callbacks.append(lambda: value_changed_callbacks.append("refresh"))
        item_model_end_subscription = model.subscribe_item_model_end_edit(
            lambda _: item_model_end_callbacks.append("end_edit")
        )

        with (
            patch.object(_model_module, "_begin_interaction", create=True) as begin_interaction,
            patch.object(_model_module, "_end_interaction", create=True) as end_interaction,
        ):
            # Act
            model._item_model_end_edit(field_model)

        # Assert
        begin_interaction.assert_not_called()
        end_interaction.assert_not_called()
        self.assertEqual(model._active_edit_model_counts, {})
        self.assertEqual(value_changed_callbacks, [])
        self.assertEqual(item_model_end_callbacks, [])
        del item_model_end_subscription

    async def test_end_property_edit_removes_stale_zero_count_and_closes_token(self):
        # Arrange
        model = USDModel(context_name="")
        token = object()
        field_model = _TabFieldModel()
        model_id = id(field_model)
        model._usd_notice_token = token
        model.supress_usd_events_during_widget_edit = True
        model._active_edit_model_counts[model_id] = 0

        with patch.object(_model_module, "_end_interaction", create=True) as end_interaction:
            # Act
            model._end_property_edit(model_id)

        # Assert
        end_interaction.assert_called_once_with(token)
        self.assertEqual(model._active_edit_model_counts, {})
        self.assertFalse(model.supress_usd_events_during_widget_edit)

    async def test_reentrant_begin_edit_waits_for_matching_final_end_edit(self):
        # Arrange
        model = USDModel(context_name="")
        token = object()
        field_model = _TabFieldModel()
        item_model_end_callbacks = []
        item_model_end_subscription = model.subscribe_item_model_end_edit(
            lambda _: item_model_end_callbacks.append("end_edit")
        )

        with (
            patch.object(_model_module, "_begin_interaction", return_value=token, create=True),
            patch.object(_model_module, "_end_interaction", create=True) as end_interaction,
        ):
            # Act
            model._on_item_model_begin_edit(field_model)
            model._on_item_model_begin_edit(field_model)
            model._item_model_end_edit(field_model)

            # Assert
            end_interaction.assert_not_called()
            self.assertTrue(model.supress_usd_events_during_widget_edit)
            self.assertEqual(item_model_end_callbacks, [])

            # Act
            model._item_model_end_edit(field_model)

            # Assert
            end_interaction.assert_not_called()
            await self._wait_for_deferred_property_edit_finish(model)
            end_interaction.assert_called_once_with(token)

        self.assertFalse(model.supress_usd_events_during_widget_edit)
        self.assertEqual(item_model_end_callbacks, ["end_edit"])
        del item_model_end_subscription

    async def test_tab_focus_transfer_skips_intermediate_end_callbacks(self):
        # Arrange
        model = USDModel(context_name="")
        token = object()
        first_field_model = _TabFieldModel()
        second_field_model = _TabFieldModel()
        value_changed_callbacks = []
        item_model_end_callbacks = []
        model._value_changed_callbacks.append(lambda: value_changed_callbacks.append("refresh"))
        item_model_end_subscription = model.subscribe_item_model_end_edit(
            lambda _: item_model_end_callbacks.append("end_edit")
        )

        with (
            patch.object(_model_module, "_begin_interaction", return_value=token, create=True) as begin_interaction,
            patch.object(_model_module, "_end_interaction", create=True) as end_interaction,
        ):
            # Act
            model._on_item_model_begin_edit(first_field_model)
            model._on_item_model_begin_edit(second_field_model)
            model._item_model_end_edit(first_field_model)

            # Assert
            begin_interaction.assert_called_once_with(model.stage)
            end_interaction.assert_not_called()
            self.assertTrue(model.supress_usd_events_during_widget_edit)
            self.assertEqual(value_changed_callbacks, [])
            self.assertEqual(item_model_end_callbacks, [])

            # Act
            model._item_model_end_edit(second_field_model)

            # Assert
            end_interaction.assert_not_called()
            await self._wait_for_deferred_property_edit_finish(model)
            end_interaction.assert_called_once_with(token)

        self.assertFalse(model.supress_usd_events_during_widget_edit)
        self.assertEqual(value_changed_callbacks, ["refresh"])
        self.assertEqual(item_model_end_callbacks, ["end_edit"])
        del item_model_end_subscription

    async def test_cancel_property_edit_interaction_flushes_active_token(self):
        # Arrange
        model = USDModel(context_name="")
        token = object()
        active_field_model = _TabFieldModel()

        with (
            patch.object(_model_module, "_begin_interaction", return_value=token, create=True),
            patch.object(_model_module, "_end_interaction", create=True) as end_interaction,
        ):
            # Act
            model._on_item_model_begin_edit(active_field_model)
            model.cancel_property_edit_interaction()

        # Assert
        end_interaction.assert_called_once_with(token)
        self.assertFalse(model.supress_usd_events_during_widget_edit)

    async def test_cancel_property_edit_interaction_flushes_active_token_when_value_cancel_fails(self):
        # Arrange
        model = USDModel(context_name="")
        token = object()
        active_field_model = _TabFieldModel()
        item = MagicMock(value_models=[_FailingCancelValueModel()])
        model.get_all_items = MagicMock(return_value=[item])

        with (
            patch.object(_model_module, "_begin_interaction", return_value=token, create=True),
            patch.object(_model_module, "_end_interaction", create=True) as end_interaction,
        ):
            model._on_item_model_begin_edit(active_field_model)

            # Act
            with self.assertRaises(RuntimeError):
                model.cancel_property_edit_interaction()

        # Assert
        end_interaction.assert_called_once_with(token)
        self.assertFalse(model.supress_usd_events_during_widget_edit)

    async def test_cancel_property_edit_interaction_ignores_child_end_edit_callbacks(self):
        # Arrange
        model = USDModel(context_name="")
        token = object()
        active_field_model = _TabFieldModel()
        item = MagicMock(
            value_models=[
                _EndingCancelValueModel(lambda: model._item_model_end_edit(active_field_model)),
            ]
        )
        value_changed_callbacks = []
        item_model_end_callbacks = []
        model.get_all_items = MagicMock(return_value=[item])
        model._value_changed_callbacks.append(lambda: value_changed_callbacks.append("refresh"))
        item_model_end_subscription = model.subscribe_item_model_end_edit(
            lambda _: item_model_end_callbacks.append("end_edit")
        )

        with (
            patch.object(_model_module, "_begin_interaction", return_value=token, create=True),
            patch.object(_model_module, "_end_interaction", create=True) as end_interaction,
        ):
            model._on_item_model_begin_edit(active_field_model)

            # Act
            model.cancel_property_edit_interaction()

        # Assert
        end_interaction.assert_called_once_with(token)
        self.assertFalse(model.supress_usd_events_during_widget_edit)
        self.assertEqual(value_changed_callbacks, [])
        self.assertEqual(item_model_end_callbacks, [])
        del item_model_end_subscription

    async def test_cancel_property_edit_interaction_suppresses_pending_attribute_created_callback(self):
        # Arrange
        model = USDModel(context_name="")
        token = object()
        attribute_created_callbacks = []
        subscription = model.subscribe_attribute_created(lambda _: attribute_created_callbacks.append("created"))

        with (
            patch.object(_model_module, "_begin_interaction", return_value=token, create=True),
            patch.object(_model_module, "_end_interaction", create=True) as end_interaction,
        ):
            model._item_attribute_create_begin_edit([Sdf.Path("/Prim.test")])

            # Act
            model.cancel_property_edit_interaction()
            model._item_attribute_create_end_edit([Sdf.Path("/Prim.test")])

        # Assert
        end_interaction.assert_called_once_with(token)
        self.assertEqual(attribute_created_callbacks, [])
        del subscription

    async def test_cancel_property_edit_interaction_suppresses_all_pending_attribute_created_callbacks(self):
        # Arrange
        model = USDModel(context_name="")
        token = object()
        attribute_created_callbacks = []
        subscription = model.subscribe_attribute_created(lambda _: attribute_created_callbacks.append("created"))

        with (
            patch.object(_model_module, "_begin_interaction", return_value=token, create=True),
            patch.object(_model_module, "_end_interaction", create=True) as end_interaction,
        ):
            model._item_attribute_create_begin_edit([Sdf.Path("/Prim.first")])
            model._item_attribute_create_begin_edit([Sdf.Path("/Prim.second")])

            # Act
            model.cancel_property_edit_interaction()
            model._item_attribute_create_end_edit([Sdf.Path("/Prim.first")])
            model._item_attribute_create_end_edit([Sdf.Path("/Prim.second")])

        # Assert
        end_interaction.assert_called_once_with(token)
        self.assertEqual(attribute_created_callbacks, [])
        del subscription

    async def test_cancel_property_edit_interaction_keeps_token_open_during_child_cancel_callbacks(self):
        # Arrange
        model = USDModel(context_name="")
        token = object()
        end_interaction_counts_during_cancel = []
        item = MagicMock(value_models=[])
        model.get_all_items = MagicMock(return_value=[item])

        with (
            patch.object(_model_module, "_begin_interaction", return_value=token, create=True),
            patch.object(_model_module, "_end_interaction", create=True) as end_interaction,
        ):

            def end_attribute_create_during_cancel():
                model._item_attribute_create_end_edit([Sdf.Path("/Prim.test")])
                end_interaction_counts_during_cancel.append(end_interaction.call_count)

            item.value_models = [_EndingCancelValueModel(end_attribute_create_during_cancel)]
            model._item_attribute_create_begin_edit([Sdf.Path("/Prim.test")])

            # Act
            model.cancel_property_edit_interaction()

        # Assert
        self.assertEqual(end_interaction_counts_during_cancel, [0])
        end_interaction.assert_called_once_with(token)


class TestVirtualAttributeWrites(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()

    async def tearDown(self):
        if self.context:
            await self.context.close_stage_async()
        self.context = None
        self.stage = None

    async def test_virtual_attribute_write_creates_missing_attribute(self):
        # Arrange
        self.stage.DefinePrim("/VirtualTestPrim")
        model = VirtualUsdAttributeValueModel(
            context_name="",
            attribute_paths=[Sdf.Path("/VirtualTestPrim.virtualFloat")],
            channel_index=0,
            value_type_name=Sdf.ValueTypeNames.Float,
            default_value=0.0,
        )

        # Act
        model.set_value(2.5)
        await omni.kit.app.get_app().next_update_async()

        # Assert
        attr = self.stage.GetAttributeAtPath("/VirtualTestPrim.virtualFloat")
        self.assertTrue(attr.IsValid())
        self.assertAlmostEqual(attr.Get(), 2.5)

    async def test_cancel_virtual_preview_removes_created_attribute(self):
        """A virtual preview restores the original absence of its property."""
        # Arrange
        self.stage.DefinePrim("/VirtualTestPrim")
        path = Sdf.Path("/VirtualTestPrim.virtualFloat")
        model = VirtualUsdAttributeValueModel("", [path], 0, Sdf.ValueTypeNames.Float, default_value=0.0)
        try:
            model.begin_batch_edit()
            model.set_value(2.5)
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            preview_value = self.stage.GetAttributeAtPath(path).Get()

            # Act
            model.cancel_property_edit_interaction()

            # Assert
            self.assertAlmostEqual(preview_value, 2.5)
            self.assertFalse(self.stage.GetAttributeAtPath(path).IsValid())
            self.assertIsNone(self.stage.GetEditTarget().GetLayer().GetPropertyAtPath(path))
            self.assertAlmostEqual(model.get_value_as_float(), 0.0)
        finally:
            model.cancel_property_edit_interaction()

    async def test_virtual_custom_callback_runs_only_on_release(self):
        """Custom creation callbacks remain release-only during numeric batches."""
        # Arrange
        self.stage.DefinePrim("/VirtualTestPrim")
        callback = MagicMock()
        model = VirtualUsdAttributeValueModel(
            "",
            [Sdf.Path("/VirtualTestPrim.virtualFloat")],
            0,
            Sdf.ValueTypeNames.Float,
            default_value=0.0,
            create_callback=callback,
        )
        try:
            # Act
            model.begin_batch_edit()
            model.set_value(2.5)
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            preview_calls = callback.call_count
            model.end_batch_edit()

            # Assert
            self.assertEqual(preview_calls, 0)
            callback.assert_called_once()
            self.assertEqual(callback.call_args.args[1], 2.5)
        finally:
            model.cancel_property_edit_interaction()

    async def test_virtual_asset_attribute_creation_normalizes_asset_value(self):
        # Arrange
        self.stage.DefinePrim("/VirtualTestPrim")
        created_values = []

        def capture_create(_attr, value):
            created_values.append(value)

        model = VirtualUsdAttributeValueModel(
            context_name="",
            attribute_paths=[Sdf.Path("/VirtualTestPrim.virtualAsset")],
            channel_index=0,
            value_type_name=Sdf.ValueTypeNames.Asset,
            default_value="",
            metadata={Sdf.PrimSpec.TypeNameKey: str(Sdf.ValueTypeNames.Asset), "colorSpace": "sRGB"},
            create_callback=capture_create,
        )

        with patch(
            "omni.flux.property_widget_builder.model.usd.item_model.attr_value._path_utils.is_file_path_valid",
            return_value=True,
        ):
            # Act
            model.set_value("textures\\diffuse.png")

        # Assert
        self.assertEqual(len(created_values), 1)
        self.assertIsInstance(created_values[0], Sdf.AssetPath)
        self.assertEqual(created_values[0].path, "textures/diffuse.png")

    async def test_virtual_attribute_write_raises_for_invalid_property_path(self):
        # Arrange
        self.stage.DefinePrim("/VirtualTestPrim")
        model = VirtualUsdAttributeValueModel(
            context_name="",
            attribute_paths=[Sdf.Path("/VirtualTestPrim.virtualFloat")],
            channel_index=0,
            value_type_name=Sdf.ValueTypeNames.Float,
            default_value=0.0,
        )
        invalid_attr = MagicMock()
        invalid_attr.GetPath.return_value = Sdf.Path("/VirtualTestPrim")

        # Act / Assert
        with self.assertRaisesRegex(ValueError, "Cannot create virtual attribute"):
            model._create_and_set_attribute_value(invalid_attr, 2.5)


class TestCurvePrimvarModelInteractiveNotices(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()
        self.prim_path = "/CurveNoticePrim"
        self.curve_id = "test:x"
        UsdGeom.Xform.Define(self.stage, self.prim_path)
        _write_curve_to_prim(
            self.stage.GetPrimAtPath(self.prim_path), self.curve_id, _curve(self.curve_id, ((0, 0), (1, 1)))
        )
        self.model = PropertyPrimvarCurveModel(
            prim_paths=[self.prim_path],
            curve_ids=[self.curve_id],
            usd_context_name="",
        )

    async def tearDown(self):
        if self.model:
            self.model.destroy()
        if self.context:
            await self.context.close_stage_async()
        self.context = None
        self.stage = None
        self.model = None

    async def test_curve_writes_flush_single_notice_when_editor_model_destroyed(self):
        # Arrange
        _commit_payload(self.model, _curve(self.curve_id, ((0.0, 0.0), (1.0, 1.0))))
        notices = []
        subscription = _register_listener(self.stage, lambda notice, stage: notices.append((notice, stage)))

        try:
            # Act
            _commit_payload(self.model, _curve(self.curve_id, ((0.0, 0.0), (0.5, 0.5), (1.0, 1.0))))
            self.model.begin_edit(self.curve_id)
            _commit_payload(self.model, _curve(self.curve_id, ((0.0, 0.0), (0.5, 0.75), (1.0, 1.0))))
            self.model.end_edit(self.curve_id)

            # Assert
            self.assertEqual(len(notices), 0)

            # Act
            self.model.destroy()
            self.model = None

            # Assert
            self.assertEqual(len(notices), 1)
        finally:
            subscription.Revoke()

    async def test_curve_notice_token_flushes_when_model_finalized(self):
        # Arrange
        _commit_payload(self.model, _curve(self.curve_id, ((0.0, 0.0), (1.0, 1.0))))
        notices = []
        subscription = _register_listener(self.stage, lambda notice, stage: notices.append((notice, stage)))

        try:
            # Act
            _commit_payload(self.model, _curve(self.curve_id, ((0.0, 0.0), (0.5, 0.25), (1.0, 1.0))))

            # Assert
            self.assertEqual(len(notices), 0)

            # Act
            self.model.__del__()

            # Assert
            self.assertEqual(len(notices), 1)
        finally:
            subscription.Revoke()

    async def test_mixed_state_recheck_ignores_unrelated_usd_notice(self):
        # Arrange
        notice = _Notice(changed_paths=["/OtherPrim.primvars:test:x:values"])

        # Act
        with patch.object(self.model, "_is_group_mixed") as mixed_check:
            self.model._on_usd_objects_changed(notice, self.stage)

        # Assert
        mixed_check.assert_not_called()

    async def test_mixed_state_recheck_runs_for_managed_curve_notice(self):
        # Arrange
        notice = _Notice(changed_paths=[f"{self.prim_path}.primvars:{self.curve_id}:values"])

        # Act
        with patch.object(self.model, "_is_group_mixed", return_value=False) as mixed_check:
            self.model._on_usd_objects_changed(notice, self.stage)

        # Assert
        mixed_check.assert_called_once()

    async def test_managed_curve_notice_notifies_with_public_curve_id(self):
        # Arrange
        notice = _Notice(changed_paths=[f"{self.prim_path}.primvars:{self.curve_id}:values"])
        notified_curve_ids = []
        subscription = self.model.subscribe(notified_curve_ids.append)

        try:
            # Act
            with patch.object(self.model, "_is_group_mixed", return_value=False):
                self.model._on_usd_objects_changed(notice, self.stage)

            # Assert
            self.assertEqual(notified_curve_ids, [self.curve_id])
        finally:
            del subscription


class TestCurvePrimvarModelMixedFirstEdit(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()
        self.prim_path = "/CurveMixedPrimA"
        self.other_prim_path = "/CurveMixedPrimB"
        self.curve_id = "test:x"
        self.model = None
        omni.kit.undo.clear_stack()
        omni.kit.undo.clear_history()

        UsdGeom.Xform.Define(self.stage, self.prim_path)
        UsdGeom.Xform.Define(self.stage, self.other_prim_path)
        _write_curve_to_prim(self.stage.GetPrimAtPath(self.prim_path), self.curve_id, _detailed_curve(self.curve_id))
        _write_curve_to_prim(
            self.stage.GetPrimAtPath(self.other_prim_path),
            self.curve_id,
            _detailed_curve(self.curve_id, middle_time=0.25, tangent_seed=0.1),
        )

    async def tearDown(self):
        if self.model:
            self.model.destroy()
        omni.kit.undo.clear_stack()
        omni.kit.undo.clear_history()
        if self.context:
            await self.context.close_stage_async()
        self.context = None
        self.stage = None
        self.model = None

    def _build_model(self) -> None:
        self.model = PropertyPrimvarCurveModel(
            prim_paths=[self.prim_path, self.other_prim_path],
            curve_ids=[self.curve_id],
            usd_context_name="",
            mixed_curve_ids={self.curve_id},
        )

    def _read_curve_payload(self, prim_path: str) -> dict:
        return _snapshot_curve_payload(self.stage.GetPrimAtPath(prim_path), self.curve_id)

    async def test_mixed_discrete_edit_flattens_and_edits_targets(self):
        # Arrange
        self._build_model()
        first_before = self._read_curve_payload(self.prim_path)
        second_before = self._read_curve_payload(self.other_prim_path)
        final_curve = _detailed_curve(self.curve_id, middle_time=0.5, tangent_seed=0.2)

        # Act
        _commit_payload(self.model, final_curve)

        # Assert
        self.assertEqual(self._read_curve_payload(self.prim_path), self._read_curve_payload(self.other_prim_path))
        self.assertNotEqual(self._read_curve_payload(self.prim_path), first_before)

        self.assertNotEqual(first_before, second_before)

    async def test_mixed_drag_flattens_on_start_and_commits_drag(self):
        # Arrange
        self._build_model()
        first_before = self._read_curve_payload(self.prim_path)
        second_before = self._read_curve_payload(self.other_prim_path)
        source_before = self._read_curve_payload(self.other_prim_path)
        final_curve = _detailed_curve(self.curve_id, middle_time=0.5, tangent_seed=0.2)

        # Act
        self.model.begin_edit(self.curve_id)

        # Assert
        self.assertEqual(self._read_curve_payload(self.prim_path), source_before)
        self.assertEqual(self._read_curve_payload(self.other_prim_path), source_before)

        # Act
        _commit_payload(self.model, final_curve)
        self.model.end_edit(self.curve_id)

        # Assert
        self.assertEqual(self._read_curve_payload(self.prim_path), self._read_curve_payload(self.other_prim_path))
        self.assertNotEqual(self._read_curve_payload(self.prim_path), source_before)

        self.assertNotEqual(first_before, second_before)

    async def test_mixed_drag_flatten_uses_generic_set_command(self):
        # Arrange
        self._build_model()

        # Act
        with patch("omni.kit.commands.execute") as execute_mock:
            self.model.begin_edit(self.curve_id)

        # Assert
        execute_mock.assert_called_once()
        self.assertEqual(execute_mock.call_args.args[0], "SetDataPrimvars")
