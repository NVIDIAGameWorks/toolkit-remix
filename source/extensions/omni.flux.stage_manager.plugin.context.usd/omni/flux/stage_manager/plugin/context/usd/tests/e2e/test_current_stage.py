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
import threading

import omni.kit.test
import omni.usd
from omni.flux.stage_manager.plugin.context.usd import CurrentStageContextPlugin
from omni.flux.stage_manager.plugin.listener.usd.stage_listener import StageManagerUSDStageListenerPlugin
from pxr import Gf, UsdGeom

__all__ = ["TestCurrentStageContextPluginConcurrency"]


class TestCurrentStageContextPluginConcurrency(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._usd_context = omni.usd.get_context()
        await self._usd_context.new_stage_async()
        self._plugin = CurrentStageContextPlugin(
            context_name="",
            listeners=[StageManagerUSDStageListenerPlugin()],
        )
        self._plugin.setup()

    async def tearDown(self):
        self._plugin.cleanup()
        if self._usd_context.can_close_stage():
            await self._usd_context.close_stage_async()

    async def test_get_items_while_xform_values_are_authored_preserves_stage_hierarchy(self):
        """Keep real context traversal stable while unrelated Xform values are authored.

        Stage Manager ignores Xform-only notices because transforms do not affect tree membership or hierarchy. This
        test runs the production context collection method on a worker while the Kit thread authors Xform values on the
        same real USD stage, guarding that accepted runtime boundary without mocks, fakes, or patched methods.
        """
        stage = self._usd_context.get_stage()
        UsdGeom.Xform.Define(stage, "/World")
        moving_xform = UsdGeom.Xform.Define(stage, "/World/Moving")
        translate_op = moving_xform.AddTranslateOp()
        for index in range(256):
            stage.DefinePrim(f"/World/Group_{index}/Child", "Xform")

        expected_paths = {str(prim.GetPath()) for prim in stage.Traverse()}
        reader_started = threading.Event()
        writing = threading.Event()
        stop_reader = threading.Event()
        read_completed_while_writing = threading.Event()

        def collect_context_items():
            latest_items = None
            reader_started.set()
            while not stop_reader.is_set():
                latest_items = self._plugin.get_items()
                if writing.is_set():
                    read_completed_while_writing.set()
            return latest_items

        reader_task = asyncio.create_task(asyncio.to_thread(collect_context_items))
        try:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 5
            while not reader_started.is_set() and loop.time() < deadline:
                await asyncio.sleep(0)
            self.assertTrue(reader_started.is_set(), "Context worker did not start")

            writing.set()
            deadline = loop.time() + 5
            offset = 0
            while not read_completed_while_writing.is_set() and loop.time() < deadline:
                for _ in range(32):
                    offset += 1
                    translate_op.Set(Gf.Vec3d(float(offset), 0.0, 0.0))
                await asyncio.sleep(0)
        finally:
            writing.clear()
            stop_reader.set()
            items = await reader_task

        self.assertTrue(read_completed_while_writing.is_set(), "Context traversal did not overlap Xform authoring")
        items_by_path = {str(item.data.GetPath()): item for item in items}
        self.assertEqual(expected_paths, set(items_by_path))
        self.assertIs(items_by_path["/World/Moving"].parent, items_by_path["/World"])
