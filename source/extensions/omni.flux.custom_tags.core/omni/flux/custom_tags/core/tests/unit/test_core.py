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

import omni.kit.undo
import omni.usd
from omni.flux.custom_tags.core import CustomTagsCore
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import wait_stage_loading
from pxr import Sdf, Usd


class TestCustomTagsCore(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.context = omni.usd.get_context("")
        await self.context.new_stage_async()

        self.stage = self.context.get_stage()
        self.root_layer = self.stage.GetRootLayer()

        self.sublayer = Sdf.Layer.CreateAnonymous()
        self.root_layer.subLayerPaths.append(self.sublayer.identifier)

        self.stage.SetEditTarget(Usd.EditTarget(self.sublayer))

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        if self.context.can_close_stage():
            await self.context.close_stage_async()

        self.sublayer = None
        self.root_layer = None
        self.stage = None
        self.context = None

    async def test_get_tag_name_valid_collection_returns_collection_name(self):
        # Arrange
        tag_name = "Test_Tag_01"
        path = Sdf.Path(f"/World/Tags/CustomTags.collection:{tag_name}")

        # Act
        value = CustomTagsCore.get_tag_name(path)

        # Assert
        self.assertEqual(value, tag_name)

    async def test_get_tag_name_invalid_collection_returns_none(self):
        # Arrange
        path = Sdf.Path("/World/Tags/CustomTags/Invalid_Collection_Path")

        # Act
        value = CustomTagsCore.get_tag_name(path)

        # Assert
        self.assertIsNone(value)

    async def test_increment_tag_name_non_existing_name_should_return_unchanged_name(self):
        # Arrange
        for has_existing_tag_names in [True, False]:
            with self.subTest(name=f"has_existing_tag_names_{has_existing_tag_names}"):
                existing_tag_names = ["Test_Tag_01", "Test_Tag_02"] if has_existing_tag_names else []
                expected_name = "Test_Tag"

                # Act
                value = CustomTagsCore.increment_tag_name(expected_name, existing_tag_names)

                # Assert
                self.assertEqual(value, expected_name)

    async def test_increment_tag_name_existing_name_should_return_incremented_name(self):
        # Arrange
        for test_data in [("Test_Tag", "Test_Tag_03"), ("Test_Tag_05", "Test_Tag_06")]:
            input_name, expected_name = test_data
            with self.subTest(name=f"input_name_{input_name}_expected_name_{expected_name}"):
                existing_tag_names = ["Test_Tag", "Test_Tag_01", "Test_Tag_02", "Test_Tag_04", "Test_Tag_05"]

                # Act
                value = CustomTagsCore.increment_tag_name(input_name, existing_tag_names)

                # Assert
                self.assertEqual(value, expected_name)

    async def test_get_unique_tag_path_create_tag_should_return_unique_path(self):
        # Arrange
        core = CustomTagsCore(context_name="")

        for test_data in [("Test_Tag", "Test_Tag_03"), ("Test_Tag_05", "Test_Tag_06")]:
            input_name, expected_name = test_data
            with self.subTest(name=f"input_name_{input_name}_expected_name_{expected_name}"):
                base_path = "/CustomTags.collection:"
                existing_tag_names = [
                    Sdf.Path(f"{base_path}Test_Tag"),
                    Sdf.Path(f"{base_path}Test_Tag_01"),
                    Sdf.Path(f"{base_path}Test_Tag_02"),
                    Sdf.Path(f"{base_path}Test_Tag_04"),
                    Sdf.Path(f"{base_path}Test_Tag_05"),
                ]

                # Act
                value = core.get_unique_tag_path(input_name, existing_tag_paths=existing_tag_names)

                # Assert
                self.assertEqual(value, Sdf.Path(f"{base_path}{expected_name}"))

    async def test_get_unique_tag_path_rename_tag_should_return_unique_path(self):
        # Arrange
        core = CustomTagsCore(context_name="")

        for test_data in [
            ("Test_Tag", Sdf.Path("/RootNode/CustomTags.collection:Original_Tag"), "Test_Tag_03"),
            ("Test_Tag_05", Sdf.Path("/RootNode/CustomTags.collection:Original_Tag_01"), "Test_Tag_06"),
        ]:
            input_name, original_path, expected_name = test_data
            with self.subTest(
                name=f"input_name_{input_name}_original_path_{original_path.name}_expected_name_{expected_name}"
            ):
                base_path = "/CustomTags.collection:"
                expected_base_path = "/RootNode/CustomTags.collection:"
                existing_tag_names = [
                    Sdf.Path(f"{base_path}Test_Tag"),
                    Sdf.Path(f"{base_path}Test_Tag_01"),
                    Sdf.Path(f"{base_path}Test_Tag_02"),
                    Sdf.Path(f"{base_path}Test_Tag_04"),
                    Sdf.Path(f"{base_path}Test_Tag_05"),
                ]

                # Act
                value = core.get_unique_tag_path(
                    input_name, current_tag_path=original_path, existing_tag_paths=existing_tag_names
                )

                # Assert
                self.assertEqual(value, Sdf.Path(f"{expected_base_path}{expected_name}"))

    async def test_get_all_tags_should_return_all_tag_collections(self):
        # Arrange
        base_path = "/CustomTags"
        tags = ["Test_Tag_01", "Test_Tag_02", "Test_Tag_03", "Test_Tag_04", "Test_Tag_05"]

        with Usd.EditContext(self.stage, self.root_layer):
            prim = self.stage.DefinePrim(base_path, "Scope")

            for tag in tags:
                Usd.CollectionAPI.Apply(prim, tag)

        core = CustomTagsCore(context_name="")

        # Act
        value = core.get_all_tags()

        # Assert
        self.assertListEqual(value, [Sdf.Path(f"{base_path}.collection:{tag}") for tag in tags])

    async def test_get_prim_tags_should_return_assigned_tags(self):
        # Arrange
        base_path = "/CustomTags"
        prims = ["/RootNode/meshes/mesh_01", "/RootNode/meshes/mesh_02", "/RootNode/meshes/mesh_03"]
        tags = ["Test_Tag_01", "Test_Tag_02", "Test_Tag_03", "Test_Tag_04", "Test_Tag_05"]

        with Usd.EditContext(self.stage, self.root_layer):
            base_prim = self.stage.DefinePrim(base_path, "Scope")

            for prim in prims:
                self.stage.DefinePrim(prim, "Xform")

            collections = []
            for tag in tags:
                collections.append(Usd.CollectionAPI.Apply(base_prim, tag))

            includes_rel = collections[0].CreateIncludesRel()
            includes_rel.AddTarget(prims[0])
            includes_rel.AddTarget(prims[1])
            includes_rel.AddTarget(prims[2])

            includes_rel = collections[1].CreateIncludesRel()
            includes_rel.AddTarget(prims[1])
            includes_rel.AddTarget(prims[2])

            includes_rel = collections[2].CreateIncludesRel()
            includes_rel.AddTarget(prims[2])

            includes_rel = collections[3].CreateIncludesRel()
            includes_rel.AddTarget(prims[2])

        core = CustomTagsCore(context_name="")

        # Act
        tags_0 = core.get_prim_tags(self.stage.GetPrimAtPath(prims[0]))
        tags_1 = core.get_prim_tags(self.stage.GetPrimAtPath(prims[1]))
        tags_2 = core.get_prim_tags(self.stage.GetPrimAtPath(prims[2]))

        # Assert
        self.assertListEqual(tags_0, [Sdf.Path(f"{base_path}.collection:{tags[0]}")])
        self.assertListEqual(
            tags_1, [Sdf.Path(f"{base_path}.collection:{tags[0]}"), Sdf.Path(f"{base_path}.collection:{tags[1]}")]
        )
        self.assertListEqual(
            tags_2,
            [
                Sdf.Path(f"{base_path}.collection:{tags[0]}"),
                Sdf.Path(f"{base_path}.collection:{tags[1]}"),
                Sdf.Path(f"{base_path}.collection:{tags[2]}"),
                Sdf.Path(f"{base_path}.collection:{tags[3]}"),
            ],
        )

    async def test_get_tag_prims_should_return_collection_members(self):
        # Arrange
        base_path = "/CustomTags"
        prims = ["/RootNode/meshes/mesh_01", "/RootNode/meshes/mesh_02", "/RootNode/meshes/mesh_03"]
        tags = ["Test_Tag_01", "Test_Tag_02", "Test_Tag_03", "Test_Tag_04", "Test_Tag_05"]

        with Usd.EditContext(self.stage, self.root_layer):
            base_prim = self.stage.DefinePrim(base_path, "Scope")

            for prim in prims:
                self.stage.DefinePrim(prim, "Xform")

            collections = []
            for tag in tags:
                collections.append(Usd.CollectionAPI.Apply(base_prim, tag))

            includes_rel = collections[0].CreateIncludesRel()
            includes_rel.AddTarget(prims[0])
            includes_rel.AddTarget(prims[1])
            includes_rel.AddTarget(prims[2])

            includes_rel = collections[1].CreateIncludesRel()
            includes_rel.AddTarget(prims[1])
            includes_rel.AddTarget(prims[2])

            includes_rel = collections[2].CreateIncludesRel()
            includes_rel.AddTarget(prims[2])

        core = CustomTagsCore(context_name="")

        # Act
        prims_0 = core.get_tag_prims(collections[0].GetCollectionPath())
        prims_1 = core.get_tag_prims(collections[1].GetCollectionPath())
        prims_2 = core.get_tag_prims(collections[2].GetCollectionPath())
        prims_3 = core.get_tag_prims(collections[3].GetCollectionPath())

        # Assert
        self.assertListEqual(prims_0, [Sdf.Path(prims[0]), Sdf.Path(prims[1]), Sdf.Path(prims[2])])
        self.assertListEqual(prims_1, [Sdf.Path(prims[1]), Sdf.Path(prims[2])])
        self.assertListEqual(prims_2, [Sdf.Path(prims[2])])
        self.assertListEqual(prims_3, [])

    async def test_prim_has_tag_should_return_proper_bool_value(self):
        # Arrange
        base_path = "/CustomTags"
        prims = ["/RootNode/meshes/mesh_01", "/render"]
        tags = ["Test_Tag_01", "Test_Tag_02", "Empty_Tag"]

        with Usd.EditContext(self.stage, self.root_layer):
            base_prim = self.stage.DefinePrim(base_path, "Scope")

            for prim in prims:
                self.stage.DefinePrim(prim, "Xform")

            collections = []
            for tag in tags:
                collections.append(Usd.CollectionAPI.Apply(base_prim, tag))

            includes_rel = collections[0].CreateIncludesRel()
            includes_rel.AddTarget(prims[0])
            includes_rel.AddTarget(prims[1])

            includes_rel = collections[1].CreateIncludesRel()
            includes_rel.AddTarget(prims[0])

        core = CustomTagsCore(context_name="")

        for test_data in [
            (prims[0], tags[0], True),
            (prims[0], tags[1], True),
            (prims[0], tags[2], False),
            (prims[1], tags[0], True),
            (prims[1], tags[1], False),
            (prims[1], tags[2], False),
        ]:
            input_prim, input_tag, expected_value = test_data
            with self.subTest(name=f"input_prim_{input_prim}_input_tag_{input_tag}_expected_value_{expected_value}"):
                prim = self.stage.GetPrimAtPath(input_prim)
                tag_path = Sdf.Path(f"{base_path}.collection:{input_tag}")

                # Act
                value = core.prim_has_tag(prim, tag_path)

                # Assert
                self.assertEqual(value, expected_value)

    async def test_create_tag_no_prim_should_create_prim_and_create_tag_collection(self):
        # Arrange
        tag_name = "Test_Tag_01"

        core = CustomTagsCore(context_name="")

        # Act
        core.create_tag(tag_name)

        # Assert
        prim_spec = self.root_layer.GetPrimAtPath("/CustomTags")
        self.assertTrue(bool(prim_spec))

        invalid_prim_spec = self.sublayer.GetPrimAtPath("/CustomTags")
        self.assertFalse(bool(invalid_prim_spec))

        collection = Usd.CollectionAPI.GetCollection(self.stage, Sdf.Path(f"{prim_spec.path}.collection:{tag_name}"))
        self.assertTrue(bool(collection))

    async def test_create_tag_existing_tags_should_create_tag_collection_with_unique_name(self):
        # Arrange
        base_path = "/CustomTags"
        tags = ["Test_Tag_01", "Test_Tag_02", "Test_Tag_04", "Test_Tag_05"]

        with Usd.EditContext(self.stage, self.root_layer):
            prim = self.stage.DefinePrim(base_path, "Scope")

            for tag in tags:
                Usd.CollectionAPI.Apply(prim, tag)

        tag_name = "Test_Tag_01"
        expected_tag_name = "Test_Tag_03"

        core = CustomTagsCore(context_name="")

        # Act
        core.create_tag(tag_name)

        # Assert
        invalid_prim_spec = self.sublayer.GetPrimAtPath("/CustomTags")
        self.assertFalse(bool(invalid_prim_spec))

        collection = Usd.CollectionAPI.GetCollection(
            self.stage, Sdf.Path(f"{base_path}.collection:{expected_tag_name}")
        )
        self.assertTrue(bool(collection))

    async def test_create_tag_no_prim_should_execute_all_commands_in_undo_group(self):
        # Arrange
        tag_name = "Test_Tag_01"

        core = CustomTagsCore(context_name="")
        core.create_tag(tag_name)

        # Act
        omni.kit.undo.undo()

        # Assert
        prim = self.stage.GetPrimAtPath("/CustomTags")
        self.assertFalse(prim.IsValid())

    async def test_rename_tag_should_rename_collection(self):
        # Arrange
        base_path = "/CustomTags"
        tags = ["Test_Tag_01", "Test_Tag_02", "Test_Tag_04", "Test_Tag_05"]

        with Usd.EditContext(self.stage, self.root_layer):
            prim = self.stage.DefinePrim(base_path, "Scope")

            for tag in tags:
                Usd.CollectionAPI.Apply(prim, tag)

        new_tag_name = "Test_Tag_02"
        expected_tag_name = "Test_Tag_03"

        core = CustomTagsCore(context_name="")

        # Act
        core.rename_tag(Sdf.Path(f"{base_path}.collection:{tags[0]}"), new_tag_name)

        # Assert
        invalid_prim_spec = self.sublayer.GetPrimAtPath("/CustomTags")
        self.assertFalse(bool(invalid_prim_spec))

        collection = Usd.CollectionAPI.GetCollection(
            self.stage, Sdf.Path(f"{base_path}.collection:{expected_tag_name}")
        )
        self.assertTrue(bool(collection))

        collection = Usd.CollectionAPI.GetCollection(self.stage, Sdf.Path(f"{base_path}.collection:{tags[0]}"))
        self.assertFalse(bool(collection))

    async def test_delete_tags_should_delete_collections(self):
        # Arrange
        base_path = "/CustomTags"
        tags = ["Test_Tag_01", "Test_Tag_02", "Test_Tag_04", "Test_Tag_05"]

        with Usd.EditContext(self.stage, self.root_layer):
            prim = self.stage.DefinePrim(base_path, "Scope")

            for tag in tags:
                Usd.CollectionAPI.Apply(prim, tag)

        delete_target = [Sdf.Path(f"{base_path}.collection:{t}") for t in tags[:2]]
        expected_result = [Sdf.Path(f"{base_path}.collection:{t}") for t in tags[2:]]

        core = CustomTagsCore(context_name="")

        # Act
        core.delete_tags(delete_target)

        # Assert
        invalid_prim_spec = self.sublayer.GetPrimAtPath("/CustomTags")
        self.assertFalse(bool(invalid_prim_spec))

        collections = Usd.CollectionAPI.GetAllCollections(self.stage.GetPrimAtPath(base_path))
        self.assertListEqual([collection.GetCollectionPath() for collection in collections], expected_result)

    async def test_add_tag_to_prim_should_add_prim_to_tag_collection(self):
        # Arrange
        base_path = "/CustomTags"
        prims = ["/RootNode/meshes/mesh_01", "/render"]
        tags = ["Test_Tag_01", "Test_Tag_02", "Empty_Tag"]

        with Usd.EditContext(self.stage, self.root_layer):
            base_prim = self.stage.DefinePrim(base_path, "Scope")

            for prim in prims:
                self.stage.DefinePrim(prim, "Xform")

            collections = []
            for tag in tags:
                collections.append(Usd.CollectionAPI.Apply(base_prim, tag))

        core = CustomTagsCore(context_name="")

        # Act
        core.add_tag_to_prim(Sdf.Path(prims[0]), Sdf.Path(f"{base_path}.collection:{tags[0]}"))
        core.add_tag_to_prim(Sdf.Path(prims[0]), Sdf.Path(f"{base_path}.collection:{tags[1]}"))
        core.add_tag_to_prim(Sdf.Path(prims[1]), Sdf.Path(f"{base_path}.collection:{tags[1]}"))

        # Assert
        includes_00 = (
            Usd.CollectionAPI.GetCollection(self.stage, Sdf.Path(f"{base_path}.collection:{tags[0]}"))
            .GetIncludesRel()
            .GetTargets()
        )
        self.assertEqual(includes_00, [Sdf.Path(p) for p in prims[:1]])

        includes_01 = (
            Usd.CollectionAPI.GetCollection(self.stage, Sdf.Path(f"{base_path}.collection:{tags[1]}"))
            .GetIncludesRel()
            .GetTargets()
        )
        self.assertEqual(includes_01, [Sdf.Path(p) for p in prims])

        includes_02 = (
            Usd.CollectionAPI.GetCollection(self.stage, Sdf.Path(f"{base_path}.collection:{tags[2]}"))
            .GetIncludesRel()
            .GetTargets()
        )
        self.assertEqual(includes_02, [])

    async def test_remove_tag_from_prim_should_remove_prim_from_tag_collection(self):
        # Arrange
        base_path = "/CustomTags"
        prims = ["/RootNode/meshes/mesh_01", "/render"]
        tags = ["Test_Tag_01", "Test_Tag_02", "Empty_Tag"]

        with Usd.EditContext(self.stage, self.root_layer):
            base_prim = self.stage.DefinePrim(base_path, "Scope")

            for prim in prims:
                self.stage.DefinePrim(prim, "Xform")

            collections = []
            for tag in tags:
                collections.append(Usd.CollectionAPI.Apply(base_prim, tag))

            includes_rel = collections[0].CreateIncludesRel()
            includes_rel.AddTarget(prims[0])

            includes_rel = collections[1].CreateIncludesRel()
            includes_rel.AddTarget(prims[0])
            includes_rel.AddTarget(prims[1])

            includes_rel = collections[2].CreateIncludesRel()
            includes_rel.AddTarget(prims[0])
            includes_rel.AddTarget(prims[1])

        core = CustomTagsCore(context_name="")

        # Act
        core.remove_tag_from_prim(Sdf.Path(prims[0]), Sdf.Path(f"{base_path}.collection:{tags[2]}"))
        core.remove_tag_from_prim(Sdf.Path(prims[1]), Sdf.Path(f"{base_path}.collection:{tags[2]}"))

        # Assert
        includes_00 = (
            Usd.CollectionAPI.GetCollection(self.stage, Sdf.Path(f"{base_path}.collection:{tags[0]}"))
            .GetIncludesRel()
            .GetTargets()
        )
        self.assertEqual(includes_00, [Sdf.Path(p) for p in prims[:1]])

        includes_01 = (
            Usd.CollectionAPI.GetCollection(self.stage, Sdf.Path(f"{base_path}.collection:{tags[1]}"))
            .GetIncludesRel()
            .GetTargets()
        )
        self.assertEqual(includes_01, [Sdf.Path(p) for p in prims])

        includes_02 = (
            Usd.CollectionAPI.GetCollection(self.stage, Sdf.Path(f"{base_path}.collection:{tags[2]}"))
            .GetIncludesRel()
            .GetTargets()
        )
        self.assertEqual(includes_02, [])
