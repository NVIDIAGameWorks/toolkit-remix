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

__all__ = ["TestEventCameraClipRangeOverride"]

from unittest.mock import MagicMock, patch

from omni.kit.test import AsyncTestCase

from lightspeed.event.camera_clip_range_override import core as _core
from lightspeed.event.camera_clip_range_override.core import EventCameraClipRangeOverride


def _make_camera_prim(path: str):
    prim = MagicMock()
    prim.IsA.return_value = True
    prim.GetPath.return_value = path
    return prim


def _make_stage(cameras=None, session_layer=None):
    cameras = cameras or []
    stage = MagicMock()
    stage.TraverseAll.return_value = cameras
    stage.GetSessionLayer.return_value = session_layer or MagicMock()
    return stage


class TestEventCameraClipRangeOverride(AsyncTestCase):
    """REMIX-4628: tests for the camera clip range override event handler."""

    async def setUp(self):
        # Patch out all carb/omni interactions during __init__ so we can
        # construct an event without standing up a real settings registry
        # or stage event stream.
        self._carb_patcher = patch.object(_core, "carb")
        mock_carb = self._carb_patcher.start()
        mock_carb.settings.get_settings.return_value.get.return_value = ""
        self._omni_patcher = patch.object(_core, "omni")
        mock_omni = self._omni_patcher.start()
        mock_omni.usd.get_context.return_value.get_stage.return_value = None
        self._event = EventCameraClipRangeOverride()

    async def tearDown(self):
        self._carb_patcher.stop()
        self._omni_patcher.stop()

    async def test_apply_override_skips_non_camera_prims(self):
        """Non-camera prims are filtered before any session-layer authoring runs."""
        # Arrange
        non_camera = MagicMock()
        non_camera.IsA.return_value = False
        session_layer = MagicMock()
        stage = _make_stage(cameras=[non_camera], session_layer=session_layer)
        override = MagicMock(enabled=True, near_clip=0.1, far_clip=500.0)

        # Act
        with patch.object(_core, "get_camera_clipping_override", return_value=override):
            self._event._apply_override(stage)

        # Assert
        session_layer.GetPrimAtPath.assert_not_called()

    async def test_apply_override_enabled_caches_pre_existing_value(self):
        """First enable for a camera with an existing session spec must cache its value."""
        # Arrange
        prim_path = "/World/Cam"
        camera = _make_camera_prim(prim_path)

        existing_attr = MagicMock()
        existing_attr.HasInfo.return_value = True
        existing_attr.default = (7.0, 9000.0)
        session_prim_spec = MagicMock()
        session_prim_spec.attributes = {"clippingRange": existing_attr}

        session_layer = MagicMock()
        session_layer.GetPrimAtPath.return_value = session_prim_spec
        stage = _make_stage(cameras=[camera], session_layer=session_layer)
        override = MagicMock(enabled=True, near_clip=0.1, far_clip=500.0)

        # Act
        with (
            patch.object(_core, "get_camera_clipping_override", return_value=override),
            patch.object(_core.Sdf, "AttributeSpec"),
        ):
            self._event._apply_override(stage)

        # Assert
        self.assertIn(prim_path, self._event._restoration_cache)
        self.assertEqual(self._event._restoration_cache[prim_path], (7.0, 9000.0))

    async def test_apply_override_enabled_caches_none_when_no_pre_existing_spec(self):
        """First enable with no session spec must cache None (so disable removes our spec)."""
        # Arrange
        prim_path = "/World/Cam"
        camera = _make_camera_prim(prim_path)
        session_layer = MagicMock()
        session_layer.GetPrimAtPath.return_value = None
        stage = _make_stage(cameras=[camera], session_layer=session_layer)
        override = MagicMock(enabled=True, near_clip=0.1, far_clip=500.0)

        new_spec = MagicMock()
        new_spec.attributes = {}

        # Act
        with (
            patch.object(_core, "get_camera_clipping_override", return_value=override),
            patch.object(_core.Sdf, "CreatePrimInLayer", return_value=new_spec),
            patch.object(_core.Sdf, "AttributeSpec"),
        ):
            self._event._apply_override(stage)

        # Assert
        self.assertIn(prim_path, self._event._restoration_cache)
        self.assertIsNone(self._event._restoration_cache[prim_path])

    async def test_apply_override_disabled_restores_cached_value_and_pops_cache(self):
        """Disable with a cached pre-existing value restores it and removes the cache entry."""
        # Arrange
        prim_path = "/World/Cam"
        camera = _make_camera_prim(prim_path)
        self._event._restoration_cache[prim_path] = (1.5, 2500.0)

        existing_attr = MagicMock()
        session_prim_spec = MagicMock()
        session_prim_spec.attributes = {"clippingRange": existing_attr}
        session_layer = MagicMock()
        session_layer.GetPrimAtPath.return_value = session_prim_spec
        stage = _make_stage(cameras=[camera], session_layer=session_layer)
        override = MagicMock(enabled=False, near_clip=0.1, far_clip=500.0)

        # Act
        with (
            patch.object(_core, "get_camera_clipping_override", return_value=override),
            patch.object(_core.Sdf, "AttributeSpec"),
        ):
            self._event._apply_override(stage)

        # Assert
        self.assertNotIn(prim_path, self._event._restoration_cache)

    async def test_apply_override_disabled_with_cached_none_removes_spec(self):
        """Disable with a cached None must remove our spec entirely."""
        # Arrange
        prim_path = "/World/Cam"
        camera = _make_camera_prim(prim_path)
        self._event._restoration_cache[prim_path] = None

        session_prim_spec = MagicMock()
        session_prim_spec.properties = {"clippingRange": MagicMock()}
        session_layer = MagicMock()
        session_layer.GetPrimAtPath.return_value = session_prim_spec
        stage = _make_stage(cameras=[camera], session_layer=session_layer)
        override = MagicMock(enabled=False, near_clip=0.1, far_clip=500.0)

        # Act
        with patch.object(_core, "get_camera_clipping_override", return_value=override):
            self._event._apply_override(stage)

        # Assert
        self.assertNotIn("clippingRange", session_prim_spec.properties)
        self.assertNotIn(prim_path, self._event._restoration_cache)

    async def test_apply_override_disabled_drops_orphaned_cache_entries(self):
        """Cache entries for prims that no longer exist on the stage must be
        cleared during the disable pass. Otherwise the fast-path check
        (`not self._restoration_cache`) would be defeated on subsequent
        HIERARCHY_CHANGED events even though the override is off."""
        # Arrange: cache has two entries; only one prim still exists on the stage.
        live_path = "/World/LiveCam"
        orphan_path = "/World/RemovedCam"
        self._event._restoration_cache[live_path] = (1.0, 100.0)
        self._event._restoration_cache[orphan_path] = (2.0, 200.0)

        live_camera = _make_camera_prim(live_path)
        session_prim_spec = MagicMock()
        session_prim_spec.attributes = {"clippingRange": MagicMock()}
        session_layer = MagicMock()
        session_layer.GetPrimAtPath.return_value = session_prim_spec
        stage = _make_stage(cameras=[live_camera], session_layer=session_layer)
        override = MagicMock(enabled=False, near_clip=0.1, far_clip=500.0)

        # Act
        with (
            patch.object(_core, "get_camera_clipping_override", return_value=override),
            patch.object(_core.Sdf, "AttributeSpec"),
        ):
            self._event._apply_override(stage)

        # Assert: the live prim's entry was popped during the loop, the
        # orphan's entry was cleared in the post-loop cleanup. Net result:
        # cache is empty, so the fast-path will fire next time.
        self.assertEqual(self._event._restoration_cache, {})

    async def test_name_property(self):
        """The event reports its canonical name for the events manager."""
        # Arrange / Act / Assert
        self.assertEqual(self._event.name, "CameraClipRangeOverride")

    async def test_schedule_apply_sets_pending_and_queues_one_task(self):
        """First _schedule_apply sets the flag and queues one deferred task.
        Subsequent calls while pending must not queue duplicate tasks."""
        # Arrange / Act
        with patch.object(_core.asyncio, "ensure_future") as mock_ensure_future:
            self._event._schedule_apply()
            self._event._schedule_apply()
            self._event._schedule_apply()

        # Assert
        self.assertTrue(self._event._apply_pending)
        self.assertEqual(mock_ensure_future.call_count, 1)

    async def test_deferred_apply_clears_pending_and_invokes_apply_override(self):
        """The deferred coroutine resets the pending flag and runs the apply."""

        # Arrange
        async def _immediate_next_update():
            return None

        stage = MagicMock()
        self._event._apply_pending = True
        self._event._stage_event_sub = MagicMock()
        self._event._context.get_stage.return_value = stage
        _core.omni.kit.app.get_app.return_value.next_update_async = _immediate_next_update

        with patch.object(self._event, "_apply_override") as mock_apply:
            # Act
            await self._event._deferred_apply()

        # Assert
        self.assertFalse(self._event._apply_pending)
        mock_apply.assert_called_once_with(stage)

    async def test_deferred_apply_skips_when_uninstalled(self):
        """If _uninstall ran while the deferred apply was sleeping,
        _apply_override must not be called on stale state."""

        # Arrange
        async def _immediate_next_update():
            return None

        self._event._apply_pending = True
        self._event._stage_event_sub = None  # uninstalled while pending
        self._event._context.get_stage.return_value = MagicMock()
        _core.omni.kit.app.get_app.return_value.next_update_async = _immediate_next_update

        with patch.object(self._event, "_apply_override") as mock_apply:
            # Act
            await self._event._deferred_apply()

        # Assert
        self.assertFalse(self._event._apply_pending)
        mock_apply.assert_not_called()

    async def test_deferred_apply_skips_when_stage_closed(self):
        """If the stage closed while the deferred apply was sleeping,
        _apply_override must not be called on a None stage."""

        # Arrange
        async def _immediate_next_update():
            return None

        self._event._apply_pending = True
        self._event._stage_event_sub = MagicMock()
        self._event._context.get_stage.return_value = None  # CLOSED ran during the wait
        _core.omni.kit.app.get_app.return_value.next_update_async = _immediate_next_update

        with patch.object(self._event, "_apply_override") as mock_apply:
            # Act
            await self._event._deferred_apply()

        # Assert
        self.assertFalse(self._event._apply_pending)
        mock_apply.assert_not_called()
