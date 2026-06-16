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
from contextlib import suppress
from unittest.mock import patch

import omni.usd
from omni.kit.test import AsyncTestCase

from lightspeed.hydra.remix.core import RemixSupport
from lightspeed.trex.viewports.manipulators.global_selection import GlobalSelection, l_apply_picking_mode


class _Selection:
    def __init__(self):
        self.selected_paths = []

    def get_selected_prim_paths(self):
        return self.selected_paths

    def set_selected_prim_paths(self, paths, _expand_in_stage):
        self.selected_paths = paths


class _UsdContext:
    def __init__(self):
        self.selection = _Selection()

    def get_selection(self):
        return self.selection


class _ViewportApi:
    def __init__(self):
        self.usd_context = _UsdContext()


class TestGlobalSelection(AsyncTestCase):
    @staticmethod
    async def _clear_singleton_remix_highlight_retry_task():
        singleton = GlobalSelection._instance
        task = singleton._remix_highlight_retry_task
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        singleton._pending_remix_highlight_paths = None
        singleton._remix_highlight_retry_task = None

    @staticmethod
    def _start_click(selection, viewport_api):
        pick_callbacks = []
        with (
            patch(
                "lightspeed.trex.viewports.manipulators.global_selection.HDREMIX_LEGACY_OBJECT_PICKING_HIGHLIGHTING",
                False,
            ),
            patch(
                "lightspeed.trex.viewports.manipulators.global_selection.hdremix_objectpicking_request",
                side_effect=lambda _x0, _y0, _x1, _y1, callback: pick_callbacks.append(callback),
            ),
            patch(
                "lightspeed.trex.viewports.manipulators.global_selection.is_remix_supported",
                return_value=(RemixSupport.SUPPORTED, ""),
            ),
        ):
            selection.add_prim_selection(
                viewport_api,
                ((10, 20), (10, 20), omni.usd.PickingMode.RESET_AND_SELECT),
            )
        return pick_callbacks[0]

    async def test_apply_picking_mode_merge_selection_preserves_existing_then_picked_order(self):
        # Arrange
        old_selection = ["/World/A"]
        picked_selection = ["/World/B"]

        # Act
        merged_selection = l_apply_picking_mode(
            old_selection,
            picked_selection,
            omni.usd.PickingMode.MERGE_SELECTION,
        )

        # Assert
        self.assertEqual(merged_selection, ["/World/A", "/World/B"])

    async def test_apply_picking_mode_merge_selection_dedupes_without_reordering_existing_paths(self):
        # Arrange
        old_selection = ["/World/A", "/World/B"]
        picked_selection = ["/World/B", "/World/C"]

        # Act
        merged_selection = l_apply_picking_mode(
            old_selection,
            picked_selection,
            omni.usd.PickingMode.MERGE_SELECTION,
        )

        # Assert
        self.assertEqual(merged_selection, ["/World/A", "/World/B", "/World/C"])

    async def test_apply_picking_mode_reset_and_select_preserves_pick_order(self):
        # Arrange
        old_selection = ["/World/A"]
        picked_selection = ["/World/C", "/World/B", "/World/C"]

        # Act
        reset_selection = l_apply_picking_mode(
            old_selection,
            picked_selection,
            omni.usd.PickingMode.RESET_AND_SELECT,
        )

        # Assert
        self.assertEqual(reset_selection, ["/World/C", "/World/B"])

    async def test_manipulator_click_selects_light_without_waiting_for_prim_pick(self):
        # Arrange
        selection = GlobalSelection()
        viewport_api = _ViewportApi()

        # Act
        selection.add_manipulator_selection(viewport_api, (10, 20), 100.0, "/World/Light")

        # Assert
        self.assertEqual(["/World/Light"], viewport_api.usd_context.selection.selected_paths)

    async def test_manipulator_click_after_prim_pick_selects_light(self):
        # Arrange
        selection = GlobalSelection()
        viewport_api = _ViewportApi()

        pick_callback = self._start_click(selection, viewport_api)
        pick_callback(["/World/Mesh"])

        # Act
        selection.add_manipulator_selection(viewport_api, (10, 20), 100.0, "/World/Light")

        # Assert
        self.assertEqual(["/World/Light"], viewport_api.usd_context.selection.selected_paths)

    async def test_prim_pick_after_manipulator_click_does_not_override_light(self):
        # Arrange
        selection = GlobalSelection()
        viewport_api = _ViewportApi()

        pick_callback = self._start_click(selection, viewport_api)

        # Act
        selection.add_manipulator_selection(viewport_api, (11, 21), 100.0, "/World/Light")
        pick_callback(["/World/Mesh"])

        # Assert
        self.assertEqual(["/World/Light"], viewport_api.usd_context.selection.selected_paths)

    async def test_selection_changed_after_manipulator_click_keeps_context_selection(self):
        # Arrange
        selection = GlobalSelection()
        viewport_api = _ViewportApi()

        selection.add_manipulator_selection(viewport_api, (10, 20), 100.0, "/World/Light")
        viewport_api.usd_context.selection.selected_paths = ["/World/Mesh"]

        with (
            patch(
                "lightspeed.trex.viewports.manipulators.global_selection.is_remix_supported",
                return_value=(RemixSupport.SUPPORTED, ""),
            ),
            patch("lightspeed.trex.viewports.manipulators.global_selection.hdremix_highlight_paths") as mock_highlight,
        ):
            # Act
            selection.on_selection_changed(viewport_api.usd_context, viewport_api, [])

        # Assert
        self.assertEqual(["/World/Mesh"], viewport_api.usd_context.selection.selected_paths)
        mock_highlight.assert_called_once_with(["/World/Mesh"])

    async def test_selection_change_skips_hdremix_highlight_when_remix_unsupported(self):
        # Arrange
        await self._clear_singleton_remix_highlight_retry_task()
        selection = GlobalSelection()
        viewport_api = _ViewportApi()
        viewport_api.usd_context.selection.selected_paths = ["/World/Mesh"]

        with (
            patch(
                "lightspeed.trex.viewports.manipulators.global_selection.is_remix_supported",
                return_value=(RemixSupport.NOT_SUPPORTED, "Remix initialization timeout"),
            ),
            patch(
                "lightspeed.trex.viewports.manipulators.global_selection.hdremix_highlight_paths",
                side_effect=AssertionError("highlight should not be called"),
            ),
        ):
            # Act
            selection.on_selection_changed(viewport_api.usd_context, viewport_api, [])
            await asyncio.sleep(0)

        # Assert
        self.assertEqual(["/World/Mesh"], viewport_api.usd_context.selection.selected_paths)
        self.assertIsNone(selection._remix_highlight_retry_task)

    async def test_selection_change_retries_hdremix_highlight_when_support_becomes_ready(self):
        # Arrange
        await self._clear_singleton_remix_highlight_retry_task()
        selection = GlobalSelection()
        viewport_api = _ViewportApi()
        viewport_api.usd_context.selection.selected_paths = ["/World/Mesh"]
        update_calls = []
        support_checks = []

        class _FakeApp:
            async def next_update_async(self):
                update_calls.append(None)

        def fake_is_remix_supported():
            support_checks.append(None)
            if len(support_checks) == 1:
                return RemixSupport.WAITING_FOR_INIT, "HdRemix.dll is not loaded into the process yet."
            return RemixSupport.SUPPORTED, ""

        with (
            patch(
                "lightspeed.trex.viewports.manipulators.global_selection.is_remix_supported",
                side_effect=fake_is_remix_supported,
            ),
            patch(
                "lightspeed.trex.viewports.manipulators.global_selection.omni.kit.app.get_app",
                return_value=_FakeApp(),
            ),
            patch("lightspeed.trex.viewports.manipulators.global_selection.hdremix_highlight_paths") as mock_highlight,
        ):
            # Act
            selection.on_selection_changed(viewport_api.usd_context, viewport_api, [])
            mock_highlight.assert_not_called()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            await selection._remix_highlight_retry_task

        # Assert
        self.assertGreaterEqual(len(update_calls), 1)
        mock_highlight.assert_any_call(["/World/Mesh"])
        self.assertIsNone(selection._pending_remix_highlight_paths)

    async def test_click_selection_skips_object_picking_until_remix_supports_requests(self):
        # Arrange
        selection = GlobalSelection()
        viewport_api = _ViewportApi()
        viewport_api.usd_context.selection.selected_paths = ["/World/Mesh"]

        with (
            patch(
                "lightspeed.trex.viewports.manipulators.global_selection.HDREMIX_LEGACY_OBJECT_PICKING_HIGHLIGHTING",
                False,
            ),
            patch(
                "lightspeed.trex.viewports.manipulators.global_selection.is_remix_supported",
                return_value=(RemixSupport.WAITING_FOR_INIT, "HdRemix.dll is not loaded into the process yet."),
            ),
            patch(
                "lightspeed.trex.viewports.manipulators.global_selection.hdremix_objectpicking_request",
                side_effect=AssertionError("object picking should be skipped until Remix support is ready"),
            ),
        ):
            # Act
            selection.add_prim_selection(
                viewport_api,
                ((10, 20), (10, 20), omni.usd.PickingMode.RESET_AND_SELECT),
            )

        # Assert
        self.assertEqual(["/World/Mesh"], viewport_api.usd_context.selection.selected_paths)

    async def test_box_selection_skips_object_picking_until_remix_supports_requests(self):
        # Arrange
        selection = GlobalSelection()
        viewport_api = _ViewportApi()
        viewport_api.usd_context.selection.selected_paths = ["/World/Mesh"]

        with (
            patch(
                "lightspeed.trex.viewports.manipulators.global_selection.HDREMIX_LEGACY_OBJECT_PICKING_HIGHLIGHTING",
                False,
            ),
            patch(
                "lightspeed.trex.viewports.manipulators.global_selection.is_remix_supported",
                return_value=(RemixSupport.WAITING_FOR_INIT, "HdRemix.dll is not loaded into the process yet."),
            ),
            patch(
                "lightspeed.trex.viewports.manipulators.global_selection.hdremix_objectpicking_request",
                side_effect=AssertionError("object picking should be skipped until Remix support is ready"),
            ),
        ):
            # Act
            selection.add_prim_selection(
                viewport_api,
                ((10, 20), (12, 22), omni.usd.PickingMode.RESET_AND_SELECT),
            )

        # Assert
        self.assertEqual(["/World/Mesh"], viewport_api.usd_context.selection.selected_paths)

    async def test_mesh_selection_change_after_new_prim_pick_is_allowed(self):
        # Arrange
        selection = GlobalSelection()
        viewport_api = _ViewportApi()

        selection.add_manipulator_selection(viewport_api, (10, 20), 100.0, "/World/Light")
        second_pick_callback = self._start_click(selection, viewport_api)

        # Act
        second_pick_callback(["/World/Mesh"])
        with patch("lightspeed.trex.viewports.manipulators.global_selection.hdremix_highlight_paths"):
            selection.on_selection_changed(viewport_api.usd_context, viewport_api, [])

        # Assert
        self.assertEqual(["/World/Mesh"], viewport_api.usd_context.selection.selected_paths)

    async def test_next_click_can_select_mesh_after_light_click(self):
        # Arrange
        selection = GlobalSelection()
        viewport_api = _ViewportApi()

        first_pick_callback = self._start_click(selection, viewport_api)
        selection.add_manipulator_selection(viewport_api, (10, 20), 100.0, "/World/Light")
        first_pick_callback(["/World/Mesh"])
        second_pick_callback = self._start_click(selection, viewport_api)

        # Act
        second_pick_callback(["/World/Mesh"])

        # Assert
        self.assertEqual(["/World/Mesh"], viewport_api.usd_context.selection.selected_paths)
