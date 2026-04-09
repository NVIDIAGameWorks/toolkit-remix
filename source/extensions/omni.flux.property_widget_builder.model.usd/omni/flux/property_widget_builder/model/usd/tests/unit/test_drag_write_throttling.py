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

import omni.kit.app
import omni.kit.test
import omni.usd
from omni.flux.property_widget_builder.model.usd.item_model.attr_value import UsdAttributeValueModel
from pxr import Sdf


def _make_model(stage, value=0.0):
    """Create a float attribute and return a UsdAttributeValueModel wrapping it."""
    prim = stage.DefinePrim("/DragTestPrim")
    attr = prim.CreateAttribute("testFloat", Sdf.ValueTypeNames.Float)
    attr.Set(value)
    return UsdAttributeValueModel(
        context_name="",
        attribute_paths=[Sdf.Path("/DragTestPrim.testFloat")],
        channel_index=0,
    )


def _usd_value(stage):
    """Read the current USD value of the test attribute."""
    return stage.GetPrimAtPath("/DragTestPrim").GetAttribute("testFloat").Get()


class TestDragWriteThrottling(omni.kit.test.AsyncTestCase):
    """Tests for the drag write throttling behaviour in UsdAttributeValueModel."""

    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()

    async def tearDown(self):
        if self.context:
            await self.context.close_stage_async()
        self.context = None
        self.stage = None

    # ------------------------------------------------------------------
    # begin_edit / end_edit flag management
    # ------------------------------------------------------------------

    async def test_begin_edit_sets_drag_flag(self):
        """begin_edit must set _is_batch_editing to True."""
        # Arrange
        model = _make_model(self.stage)

        # Act
        model.begin_edit()

        # Assert
        self.assertTrue(model._is_batch_editing)

    async def test_end_edit_clears_drag_flag(self):
        """end_edit must clear _is_batch_editing to False."""
        # Arrange
        model = _make_model(self.stage)
        model.begin_edit()

        # Act
        model.end_edit()

        # Assert
        self.assertFalse(model._is_batch_editing)

    # ------------------------------------------------------------------
    # set_value outside drag — synchronous path unchanged
    # ------------------------------------------------------------------

    async def test_set_value_outside_drag_writes_immediately(self):
        """set_value without an active drag must write to USD synchronously."""
        # Arrange
        model = _make_model(self.stage, value=0.0)

        # Act
        model.set_value(42.0)

        # Assert — no frame tick needed
        self.assertAlmostEqual(_usd_value(self.stage), 42.0)
        self.assertIsNone(model._pending_batch_write_task)

    # ------------------------------------------------------------------
    # set_value during drag — deferred path
    # ------------------------------------------------------------------

    async def test_set_value_during_drag_does_not_write_immediately(self):
        """During a drag, set_value must NOT write to USD before the next frame."""
        # Arrange
        model = _make_model(self.stage, value=0.0)
        model.begin_edit()

        # Act
        model.set_value(99.0)

        # Assert — USD must still hold the original value
        self.assertAlmostEqual(_usd_value(self.stage), 0.0)

    async def test_set_value_during_drag_schedules_task(self):
        """During a drag, set_value must schedule a pending async write task."""
        # Arrange
        model = _make_model(self.stage, value=0.0)
        model.begin_edit()

        # Act
        model.set_value(5.0)

        # Assert
        self.assertIsNotNone(model._pending_batch_write_task)

    async def test_rapid_set_value_throttles_to_one_task(self):
        """Multiple set_value calls in one frame must cancel earlier tasks, keeping only the latest."""
        # Arrange
        model = _make_model(self.stage, value=0.0)
        model.begin_edit()

        # Act — capture each task reference before the next call replaces it
        model.set_value(1.0)
        task1 = model._pending_batch_write_task
        model.set_value(2.0)
        task2 = model._pending_batch_write_task
        model.set_value(3.0)
        task3 = model._pending_batch_write_task
        # Yield one event loop tick so cancellations are delivered to task1 and task2
        await asyncio.sleep(0)

        # Assert — first two are cancelled, only the last one is live
        self.assertTrue(task1.cancelled())
        self.assertTrue(task2.cancelled())
        self.assertIsNotNone(task3)
        self.assertFalse(task3.cancelled())

    async def test_deferred_write_fires_after_frame(self):
        """After one frame tick the deferred write must reach USD with the latest value."""
        # Arrange
        model = _make_model(self.stage, value=0.0)
        model.begin_edit()
        model.set_value(1.0)
        model.set_value(2.0)
        model.set_value(7.0)

        # Act — yield two frames to let the deferred coroutine run
        await omni.kit.app.get_app().next_update_async()
        await omni.kit.app.get_app().next_update_async()

        # Assert — only the last value must have been written
        self.assertAlmostEqual(_usd_value(self.stage), 7.0)

    # ------------------------------------------------------------------
    # end_edit flush — synchronous final write
    # ------------------------------------------------------------------

    async def test_end_edit_flushes_pending_value(self):
        """end_edit must cancel the pending task and synchronously flush the final value to USD."""
        # Arrange
        model = _make_model(self.stage, value=0.0)
        model.begin_edit()
        model.set_value(55.0)

        # Act — end before the frame tick
        model.end_edit()

        # Assert
        self.assertAlmostEqual(_usd_value(self.stage), 55.0)
        self.assertIsNone(model._pending_batch_write_task)

    async def test_end_edit_cancels_pending_task(self):
        """end_edit must cancel the in-flight deferred task."""
        # Arrange
        model = _make_model(self.stage, value=0.0)
        model.begin_edit()
        model.set_value(10.0)
        task = model._pending_batch_write_task

        # Act
        model.end_edit()
        # Yield one event loop tick so the cancellation is delivered
        await asyncio.sleep(0)

        # Assert
        self.assertTrue(task.cancelled())

    async def test_end_edit_clears_drag_flag_even_if_stage_missing(self):
        """_is_batch_editing must be cleared by end_edit even when the stage is gone."""
        # Arrange
        model = _make_model(self.stage, value=0.0)
        model.begin_edit()
        model.set_value(1.0)
        model._stage = None  # simulate destroyed stage

        # Act
        model.end_edit()

        # Assert
        self.assertFalse(model._is_batch_editing)

    # ------------------------------------------------------------------
    # __del__ cleanup
    # ------------------------------------------------------------------

    async def test_del_cancels_pending_task(self):
        """__del__ must cancel a pending drag write task to prevent stale writes."""
        # Arrange
        model = _make_model(self.stage, value=0.0)
        model.begin_edit()
        model.set_value(3.0)
        task = model._pending_batch_write_task

        # Act
        model.__del__()
        # Yield one event loop tick so the cancellation is delivered
        await asyncio.sleep(0)

        # Assert
        self.assertTrue(task.cancelled())
        self.assertIsNone(model._pending_batch_write_task)

    async def test_del_is_safe_with_no_pending_task(self):
        """__del__ must not raise when there is no pending task."""
        # Arrange
        model = _make_model(self.stage, value=0.0)

        # Act + Assert — no exception must be raised
        try:
            model.__del__()
        except Exception as exc:  # noqa: BLE001
            self.fail(f"__del__ raised unexpectedly: {exc}")
