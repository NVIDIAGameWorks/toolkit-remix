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

import omni.kit.test
from lightspeed.trex.utils.common.prim_utils import get_prototype
from pxr import Usd


class TestGetPrototype(omni.kit.test.AsyncTestCase):
    def setUp(self):
        self.stage = Usd.Stage.CreateInMemory()
        self.stage.DefinePrim("/RootNode", "Xform")
        self.stage.DefinePrim("/RootNode/meshes", "Xform")
        self.stage.DefinePrim("/RootNode/meshes/mesh_0123456789ABCDEF", "Xform")
        self.stage.DefinePrim("/RootNode/meshes/mesh_0123456789ABCDEF/hovercraft", "Mesh")

    def test_get_prototype_of_prim_within_instance_path_should_return_equivalent_prototype_prim(self):
        # Arrange
        self.stage.DefinePrim("/RootNode/instances", "Xform")
        inst_prim = self.stage.DefinePrim("/RootNode/instances/inst_0123456789ABCDEF_0", "Xform")

        # Act
        result = get_prototype(inst_prim)

        # Assert
        self.assertIsNotNone(result)
        prototype_prim = self.stage.GetPrimAtPath("/RootNode/meshes/mesh_0123456789ABCDEF")
        self.assertEqual(result, prototype_prim)
        self.assertEqual(str(result.GetPath()), "/RootNode/meshes/mesh_0123456789ABCDEF")

    def test_get_prototype_of_child_prim_within_instance_path_should_return_equivalent_prototype_child_prim(self):
        # Arrange
        self.stage.DefinePrim("/RootNode/instances", "Xform")
        self.stage.DefinePrim("/RootNode/instances/inst_0123456789ABCDEF_0", "Xform")
        child_prim = self.stage.DefinePrim("/RootNode/instances/inst_0123456789ABCDEF_0/hovercraft", "Xform")

        # Act
        result = get_prototype(child_prim)

        # Assert
        self.assertIsNotNone(result)
        expected_prototype_child = self.stage.GetPrimAtPath("/RootNode/meshes/mesh_0123456789ABCDEF/hovercraft")
        self.assertEqual(result, expected_prototype_child)
        self.assertEqual(str(result.GetPath()), "/RootNode/meshes/mesh_0123456789ABCDEF/hovercraft")

    def test_get_prototype_of_prototype_prim_should_return_itself_idempotent(self):
        # Arrange
        prototype_prim = self.stage.GetPrimAtPath("/RootNode/meshes/mesh_0123456789ABCDEF")

        # Act
        result = get_prototype(prototype_prim)

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result, prototype_prim)
        self.assertEqual(str(result.GetPath()), "/RootNode/meshes/mesh_0123456789ABCDEF")

    def test_get_prototype_of_child_prim_within_prototype_path_should_return_itself_idempotent(self):
        # Arrange
        child_prototype_prim = self.stage.DefinePrim("/RootNode/meshes/mesh_0123456789ABCDEF/hovercraft", "Xform")

        # Act
        result = get_prototype(child_prototype_prim)

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result, child_prototype_prim)
        self.assertEqual(str(result.GetPath()), "/RootNode/meshes/mesh_0123456789ABCDEF/hovercraft")

    def test_get_prototype_of_invalid_prim_should_return_none(self):
        # Arrange
        invalid_prim = self.stage.GetPrimAtPath("/InvalidPath")

        # Act
        result = get_prototype(invalid_prim)

        # Assert
        self.assertIsNone(result)

    def test_get_prototype_of_non_matching_prim_should_return_itself(self):
        # Arrange
        non_matching_prim = self.stage.DefinePrim("/RootNode/SomeOtherPath", "Xform")

        # Act
        result = get_prototype(non_matching_prim)

        # Assert
        self.assertEqual(non_matching_prim, result)

    def test_get_prototype_of_inst_prim_without_prototype_equivalent_should_return_none(self):
        # Arrange
        self.stage.DefinePrim("/RootNode/instances", "Xform")
        inst_prim = self.stage.DefinePrim("/RootNode/instances/inst_DEADBEEF0BADC0DE_0", "Xform")

        # Act
        result = get_prototype(inst_prim)

        # Assert
        self.assertIsNone(result)
