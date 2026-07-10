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

from unittest.mock import MagicMock, patch

import omni.kit.app
import omni.kit.undo
import omni.kit.test
import omni.usd
from omni.flux.fcurve.widget import FCurve, FCurveKey, InfinityType, TangentType
from omni.flux.curve_editor.widget.payload import curve_to_payload
from omni.flux.property_widget_builder.model.usd import model as _model_module
from omni.flux.property_widget_builder.model.usd.curve_primvar import PropertyPrimvarCurveModel
from omni.flux.property_widget_builder.model.usd.logical_group_constants import CURVE_LOGICAL_GROUP_DEFINITION
from omni.flux.property_widget_builder.model.usd.item_model.attr_value import UsdAttributeValueModel
from omni.flux.property_widget_builder.model.usd.item_model.attr_value import VirtualUsdAttributeValueModel
from omni.flux.property_widget_builder.model.usd.model import USDModel
from omni.flux.property_widget_builder.widget import ItemGroup
from omni.flux.utils.common.interactive_usd_notices import register_objects_changed_listener as _register_listener
from pxr import Sdf, UsdGeom


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


class _SetItemsCancelValueModel:
    def __init__(self):
        self.callbacks = (None, None)

    def set_property_edit_callbacks(self, begin_callback, end_callback):
        self.callbacks = (begin_callback, end_callback)

    def cancel_property_edit_interaction(self):
        raise RuntimeError("cancel failure")

    def refresh(self):
        pass


class _SetItemsValueModel:
    def __init__(self):
        self.callbacks = (None, None)

    def set_property_edit_callbacks(self, begin_callback, end_callback):
        self.callbacks = (begin_callback, end_callback)

    def cancel_property_edit_interaction(self):
        pass

    def refresh(self):
        pass


class _Notice:
    def __init__(self, changed_paths=(), resynced_paths=()):
        self._changed_paths = list(changed_paths)
        self._resynced_paths = list(resynced_paths)

    def GetChangedInfoOnlyPaths(self):  # noqa: N802 - mimic USD API
        return self._changed_paths

    def GetResyncedPaths(self):  # noqa: N802 - mimic USD API
        return self._resynced_paths


class TestUsdAttributeValueModelEditBatching(omni.kit.test.AsyncTestCase):
    """Regression tests for deferred edit writes in UsdAttributeValueModel."""

    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()

    async def tearDown(self):
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

        with patch("omni.kit.undo.begin_group"), patch("omni.kit.undo.end_group"):
            model.begin_batch_edit()

            # Act
            model.set_value(5.0)

            # Assert
            self.assertAlmostEqual(model.get_value_as_float(), 5.0)
            self.assertAlmostEqual(_usd_value(self.stage), 0.0)

    async def test_end_batch_edit_flushes_only_the_final_drag_value(self):
        # Arrange
        model = _make_model(self.stage, value=0.0)

        with patch("omni.kit.undo.begin_group") as begin_group, patch("omni.kit.undo.end_group") as end_group:
            model.begin_batch_edit()
            model.set_value(10.0)
            self.assertAlmostEqual(_usd_value(self.stage), 0.0)
            model.set_value(20.0)
            self.assertAlmostEqual(_usd_value(self.stage), 0.0)
            model.set_value(30.0)
            self.assertAlmostEqual(_usd_value(self.stage), 0.0)

            # Act
            model.end_batch_edit()

            # Assert
            begin_group.assert_called_once_with()
            end_group.assert_called_once_with()
            self.assertAlmostEqual(_usd_value(self.stage), 30.0)

    async def test_cancel_property_edit_interaction_aborts_active_batch_edit(self):
        # Arrange
        model = _make_model(self.stage, value=0.0)

        with patch("omni.kit.undo.begin_group"), patch("omni.kit.undo.end_group") as end_group:
            model.begin_batch_edit()
            model.set_value(7.0)

            # Act
            model.cancel_property_edit_interaction()

            # Assert
            end_group.assert_called_once_with()
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
        model.set_property_edit_callbacks(None, lambda value_model: end_calls.append(value_model))
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

    async def test_end_batch_edit_records_single_undoable_change(self):
        # Arrange
        omni.kit.undo.clear_stack()
        omni.kit.undo.clear_history()
        model = _make_model(self.stage, value=0.0)

        try:
            # Act
            model.begin_batch_edit()
            model.set_value(10.0)
            model.set_value(20.0)
            model.set_value(30.0)
            model.end_batch_edit()

            # Assert
            change_property_entries = [
                entry for entry in omni.kit.undo.get_history().values() if entry.name == "ChangeProperty"
            ]
            self.assertEqual(len(change_property_entries), 1)
            self.assertAlmostEqual(_usd_value(self.stage), 30.0)

            omni.kit.undo.undo()
            self.assertAlmostEqual(_usd_value(self.stage), 0.0)
        finally:
            omni.kit.undo.clear_stack()
            omni.kit.undo.clear_history()


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

    async def test_set_items_replaces_items_before_reraising_cancel_failure(self):
        # Arrange
        model = USDModel(context_name="")
        value_model = _SetItemsCancelValueModel()
        old_item = ItemGroup("old", expanded=True)
        old_item._value_models = [value_model]
        new_value_model = _SetItemsValueModel()
        new_item = ItemGroup("new", expanded=True)
        new_item._value_models = [new_value_model]
        model.set_items([old_item])
        self.assertNotEqual(value_model.callbacks, (None, None))

        # Act
        with self.assertRaisesRegex(RuntimeError, "cancel failure"):
            model.set_items([new_item])

        # Assert
        self.assertEqual(value_model.callbacks, (None, None))
        self.assertNotEqual(new_value_model.callbacks, (None, None))
        self.assertEqual(model.get_all_items(), [new_item])


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
