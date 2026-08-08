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

import omni.kit.test
import omni.usd
from omni.flux.stage_manager.plugin.context.usd import CurrentStageContextPlugin
from omni.flux.stage_manager.plugin.listener.usd.stage_listener import StageManagerUSDStageListenerPlugin
from pxr import Gf, UsdGeom

__all__ = ["TestCurrentStageContextPluginE2E"]


class TestCurrentStageContextPluginE2E(omni.kit.test.AsyncTestCase):
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

    async def test_worker_get_items_before_and_after_xform_authoring_preserves_stage_hierarchy(self):
        """Collect the real stage on a worker only while the stage is stable."""
        stage = self._usd_context.get_stage()
        UsdGeom.Xform.Define(stage, "/World")
        moving_xform = UsdGeom.Xform.Define(stage, "/World/Moving")
        translate_op = moving_xform.AddTranslateOp()

        expected_paths = {str(prim.GetPath()) for prim in stage.Traverse()}
        before_authoring = await asyncio.to_thread(self._plugin.get_items)

        translate_op.Set(Gf.Vec3d(1.0, 0.0, 0.0))
        after_authoring = await asyncio.to_thread(self._plugin.get_items)

        for items in (before_authoring, after_authoring):
            items_by_path = {str(item.data.GetPath()): item for item in items}
            self.assertEqual(expected_paths, set(items_by_path))
            self.assertIs(items_by_path["/World/Moving"].parent, items_by_path["/World"])
