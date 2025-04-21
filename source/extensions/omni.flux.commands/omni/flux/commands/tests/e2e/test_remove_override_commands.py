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

import omni.kit.commands
import omni.kit.test
import omni.kit.undo
import omni.usd
from omni.kit.test_suite.helpers import get_test_data_path
from pxr import Sdf, Usd


class TestRemoveOverrideCommands(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    async def __define_prim(self) -> "Usd.Prim":
        test_path = omni.usd.get_stage_next_free_path(self.stage, "/World/TestPrim", False)
        return self.stage.DefinePrim(test_path, "Xform")

    async def __layer_setup(self):
        layer0 = Sdf.Layer.CreateAnonymous()
        layer1 = Sdf.Layer.CreateAnonymous()
        self.stage.GetRootLayer().subLayerPaths.append(layer0.identifier)
        self.stage.GetRootLayer().subLayerPaths.append(layer1.identifier)
        # We need a layer to create the asset on
        prims = []
        with Usd.EditContext(self.stage, layer0):
            root_prim = await self.__define_prim()
            prims.append(root_prim)
            prims.append(self.stage.DefinePrim(f"{root_prim.GetPath()}/OtherA", "Xform"))
            prims.append(self.stage.DefinePrim(f"{root_prim.GetPath()}/OtherA/OtherB", "Xform"))
            prims.append(self.stage.DefinePrim(f"{root_prim.GetPath()}/OtherA/OtherB/OtherC", "Xform"))
            prims.append(self.stage.DefinePrim("/TestA", "Xform"))

        return layer1, prims

    async def test_remove_override_keep_empty_references(self):
        layer1, prims = await self.__layer_setup()
        root_prim = prims[0]
        with Usd.EditContext(self.stage, layer1):
            light_path = str(root_prim.GetPath().AppendPath("light01"))
            omni.kit.commands.execute("CreatePrim", prim_type="RectLight", prim_path=light_path)
        # Create a reference
        cube_path = get_test_data_path(__name__, "usd/mesh.usda")
        ref_path = str(root_prim.GetPath().AppendPath("ref01"))
        omni.kit.commands.execute(
            "CreateReference",
            usd_context=omni.usd.get_context(),
            path_to=ref_path,
            asset_path=cube_path.replace("\\", "/"),
        )

        # Remove references
        ref_prim = self.stage.GetPrimAtPath(ref_path)
        ref_prim.GetReferences().ClearReferences()

        context = omni.usd.get_context()
        omni.kit.commands.execute(
            "SelectPrims", old_selected_paths=[], new_selected_paths=[light_path], expand_in_stage=True
        )
        paths = context.get_selection().get_selected_prim_paths()
        self.assertEqual(paths, [light_path])

        # Delete the prim
        omni.kit.commands.execute(
            "DeletePrims",
            paths=[light_path],
            context_name=context.get_name(),
        )

        # Remove the override
        omni.kit.commands.execute("RemoveOverride", prim_path=root_prim.GetPath(), layer=layer1, context_name="")

        # Make sure that the references are still empty now
        references = ref_prim.GetPrimIndex().rootNode.children
        self.assertEqual(references, [])

        for prim in prims:
            self.assertIsNotNone(self.stage.GetPrimAtPath(prim.GetPath()))
