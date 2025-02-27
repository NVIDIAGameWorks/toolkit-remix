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
from pxr import Sdf, Usd, UsdGeom


class TestCustomCommands(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    async def test_set_default_prim_command_do_no_previous_default(self):
        # Arrange
        root_prim = await self.__define_prim()
        self.assertFalse(self.stage.HasDefaultPrim())

        # Act
        omni.kit.commands.execute("SetDefaultPrim", prim_path=str(root_prim.GetParent().GetPath()), stage=self.stage)

        # Assert
        self.assertTrue(self.stage.HasDefaultPrim())
        self.assertEqual(self.stage.GetDefaultPrim(), root_prim.GetParent())

    async def test_set_default_prim_command_do_override_previous_default(self):
        # Arrange
        root_prim_1 = await self.__define_prim()
        root_prim_2 = await self.__define_prim()

        self.stage.SetDefaultPrim(root_prim_1.GetParent())
        self.assertTrue(self.stage.HasDefaultPrim())
        self.assertEqual(self.stage.GetDefaultPrim(), root_prim_1.GetParent())

        # Act
        omni.kit.commands.execute("SetDefaultPrim", prim_path=str(root_prim_2.GetParent().GetPath()), stage=self.stage)

        # Assert
        self.assertTrue(self.stage.HasDefaultPrim())
        self.assertEqual(self.stage.GetDefaultPrim(), root_prim_2.GetParent())

    async def test_set_default_prim_command_undo(self):
        # Arrange
        root_prim_1 = await self.__define_prim()
        root_prim_2 = await self.__define_prim()

        self.stage.SetDefaultPrim(root_prim_1.GetParent())
        self.assertTrue(self.stage.HasDefaultPrim())
        self.assertEqual(self.stage.GetDefaultPrim(), root_prim_1.GetParent())

        # Act
        omni.kit.commands.execute("SetDefaultPrim", prim_path=str(root_prim_2.GetParent().GetPath()), stage=self.stage)
        omni.kit.undo.undo()

        # Assert
        self.assertTrue(self.stage.HasDefaultPrim())
        self.assertEqual(self.stage.GetDefaultPrim(), root_prim_1.GetParent())

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

    async def __multiple_attribute_edits(self, layer: Sdf.Layer, root_prim: "Usd.Prim"):
        with Usd.EditContext(self.stage, layer):
            attribute = self.stage.GetPropertyAtPath(root_prim.GetPath().AppendProperty("visibility"))
            # Change visibility on current layer
            omni.kit.commands.execute(
                "ChangeProperty",
                prop_path=attribute.GetPath(),
                value=UsdGeom.Tokens.invisible,
                prev=UsdGeom.Tokens.visible,
            )
            # Changing purpose attr value
            other_attribute = self.stage.GetPropertyAtPath(root_prim.GetPath().AppendProperty("purpose"))
            omni.kit.commands.execute(
                "ChangeProperty",
                prop_path=other_attribute.GetPath(),
                value="test",
                prev="default",
            )

        return attribute, other_attribute

    async def test_remove_override_do(self):
        layer1, prims = await self.__layer_setup()
        root_prim = prims[0]
        attribute, other_attribute = await self.__multiple_attribute_edits(layer1, root_prim)
        self.assertEqual(attribute.Get(), UsdGeom.Tokens.invisible)
        self.assertEqual(other_attribute.Get(), "test")

        # Remove the override
        omni.kit.commands.execute(
            "RemoveOverride", prim_path=root_prim.GetPath(), layer=layer1, context_name="", attribute=attribute
        )

        # Assert that value is now visible
        self.assertEqual(attribute.Get(), UsdGeom.Tokens.inherited)
        self.assertEqual(other_attribute.Get(), "test")

    async def test_remove_override_undo(self):
        layer1, prims = await self.__layer_setup()
        root_prim = prims[0]
        # And then a layer to do the work on
        attribute, other_attribute = await self.__multiple_attribute_edits(layer1, root_prim)

        # Remove the override
        omni.kit.commands.execute(
            "RemoveOverride", prim_path=root_prim.GetPath(), layer=layer1, context_name="", attribute=attribute
        )
        self.assertEqual(attribute.Get(), UsdGeom.Tokens.inherited)
        self.assertEqual(other_attribute.Get(), "test")

        # Undo
        omni.kit.undo.undo()

        # Assert that value is invisible again
        self.assertEqual(attribute.Get(), UsdGeom.Tokens.invisible)
        self.assertEqual(other_attribute.Get(), "test")

    async def test_remove_attribute_with_non_empty_children_override(self):
        layer1, prims = await self.__layer_setup()
        root_prim = prims[0]
        with Usd.EditContext(self.stage, layer1):
            attribute = self.stage.GetPropertyAtPath(root_prim.GetPath().AppendProperty("visibility"))
            # Change visibility on current layer
            omni.kit.commands.execute(
                "ChangeProperty",
                prop_path=attribute.GetPath(),
                value=UsdGeom.Tokens.invisible,
                prev=UsdGeom.Tokens.visible,
            )
            attribute2 = self.stage.GetPropertyAtPath(prims[2].GetPath().AppendProperty("visibility"))
            # Change visibility on current layer for unrelated prim
            omni.kit.commands.execute(
                "ChangeProperty",
                prop_path=attribute2.GetPath(),
                value=UsdGeom.Tokens.invisible,
                prev=UsdGeom.Tokens.visible,
            )

        # Remove the override
        omni.kit.commands.execute(
            "RemoveOverride",
            prim_path=root_prim.GetPath(),
            layer=layer1,
            context_name="",
            attribute=attribute,
            check_up_to_prim=root_prim.GetPath(),
        )

        # Should be empty because we removed the override
        stack = attribute.GetPropertyStack(Usd.TimeCode.Default())
        # Should hold one change, since we didn't remove the override
        stack2 = attribute2.GetPropertyStack(Usd.TimeCode.Default())

        self.assertEqual(len(stack), 0)
        self.assertEqual(len(stack2), 1)

    async def test_remove_override_on_root_prim_and_cleanup_empty_child_prims(self):
        layer1, prims = await self.__layer_setup()
        root_prim = prims[0]
        with Usd.EditContext(self.stage, layer1):
            light_path = str(root_prim.GetPath().AppendPath("light01"))
            omni.kit.commands.execute("CreatePrim", prim_type="RectLight", prim_path=light_path)

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

        attrs = root_prim.GetAttributes()
        overrides = []
        for attr in attrs:
            stack = attr.GetPropertyStack(Usd.TimeCode.Default())
            if stack:
                overrides.append(1)

        self.assertEqual(len(overrides), 0)

        for prim in prims:
            self.assertIsNotNone(self.stage.GetPrimAtPath(prim.GetPath()))

    async def test_remove_override_in_middle_of_hierarchy(self):
        layer1, prims = await self.__layer_setup()
        root_prim = prims[0]
        with Usd.EditContext(self.stage, layer1):
            # Change visibility on root prim
            attribute = self.stage.GetPropertyAtPath(root_prim.GetPath().AppendProperty("visibility"))
            omni.kit.commands.execute(
                "ChangeProperty",
                prop_path=attribute.GetPath(),
                value=UsdGeom.Tokens.invisible,
                prev=UsdGeom.Tokens.visible,
            )
            # A second attribute to check to make sure that it's not removed with RemoveOverride command
            other_attribute = self.stage.GetPropertyAtPath(root_prim.GetPath().AppendProperty("purpose"))
            omni.kit.commands.execute(
                "ChangeProperty",
                prop_path=other_attribute.GetPath(),
                value="test",
                prev="default",
            )

            # Change visibility on middle of hierarchy prim
            attribute2 = self.stage.GetPropertyAtPath(prims[2].GetPath().AppendProperty("visibility"))
            omni.kit.commands.execute(
                "ChangeProperty",
                prop_path=attribute2.GetPath(),
                value=UsdGeom.Tokens.invisible,
                prev=UsdGeom.Tokens.visible,
            )

            # Change visibility on middle of hierarchy prim
            attribute2 = self.stage.GetPropertyAtPath(prims[2].GetPath().AppendProperty("visibility"))
            omni.kit.commands.execute(
                "ChangeProperty",
                prop_path=attribute2.GetPath(),
                value=UsdGeom.Tokens.invisible,
                prev=UsdGeom.Tokens.visible,
            )

        # Remove the override
        omni.kit.commands.execute(
            "RemoveOverride", prim_path=prims[2].GetPath(), layer=layer1, context_name="", attribute=attribute2
        )

        stack = attribute.GetPropertyStack(Usd.TimeCode.Default())
        stack2 = attribute2.GetPropertyStack(Usd.TimeCode.Default())

        # Should still have an override
        self.assertEqual(len(stack), 1)
        # Should be empty because we removed the override and prim
        self.assertEqual(len(stack2), 0)
