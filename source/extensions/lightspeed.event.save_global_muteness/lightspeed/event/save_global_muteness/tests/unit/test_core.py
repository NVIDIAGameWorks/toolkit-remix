"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import omni.kit.app
import omni.usd
from omni.kit.test import AsyncTestCase
from pxr import Usd


class TestCore(AsyncTestCase):
    async def test_mute_event(self):
        context = omni.usd.get_context()
        stage = Usd.Stage.CreateInMemory("test.usd")
        await context.attach_stage_async(stage)

        self.assertFalse(context.has_pending_edit())

        # we create a layer and add it
        stage_layer = Usd.Stage.CreateInMemory("layer.usd")
        layer = stage_layer.GetRootLayer()
        stage.GetRootLayer().subLayerPaths.insert(0, layer.identifier)

        self.assertTrue(context.has_pending_edit())
        # reset
        context.set_pending_edit(False)
        self.assertFalse(context.has_pending_edit())

        # now we mute the layer.
        stage.MuteLayer(layer.identifier)
        # wait for the event
        await omni.kit.app.get_app().next_update_async()
        # we should have a pending edit
        self.assertTrue(context.has_pending_edit())
