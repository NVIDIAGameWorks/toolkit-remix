"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import omni.kit.app
import omni.usd
from omni.kit.test.async_unittest import AsyncTestCase
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
