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

from unittest.mock import Mock, call, patch

import omni.kit.test
from omni.flux.validator.plugin.check.usd.material.default_material import DefaultMaterial
from pxr import UsdGeom, UsdShade


class TestDefaultMaterials(omni.kit.test.AsyncTestCase):
    class TestStage:
        async def _create_test_mesh(
            self, stage, path, vertices, face_indices, subset_indices=None, material_binding=None
        ):
            mesh = UsdGeom.Mesh.Define(stage, path)
            geom = UsdGeom.Imageable(mesh.GetPrim())
            mesh.CreatePointsAttr(vertices)
            mesh.CreateFaceVertexCountsAttr([len(indices) for indices in face_indices])
            mesh.CreateFaceVertexIndicesAttr([index for indices in face_indices for index in indices])

            bind_material = bool(material_binding)

            if subset_indices:
                for subset_index, _face_indices in enumerate(subset_indices):
                    subset = UsdGeom.Subset.CreateGeomSubset(
                        geom, "subset" + str(subset_index), UsdGeom.Tokens.face, _face_indices
                    )
                    if bind_material:
                        # only bind material to the first geomsubset
                        bind_material = False
                        UsdShade.MaterialBindingAPI(subset).Bind(material_binding)
            elif bind_material:
                UsdShade.MaterialBindingAPI(mesh).Bind(material_binding)

            return mesh.GetPrim()

        async def _create_test_stage(self):
            await omni.usd.get_context(self._context_name).new_stage_async()
            stage = omni.usd.get_context(self._context_name).get_stage()

            UsdGeom.Xform.Define(stage, "/World").GetPrim()
            UsdGeom.Xform.Define(stage, "/World/object_subset_test")
            UsdGeom.Xform.Define(stage, "/World/object_mesh_test")
            UsdGeom.Xform.Define(stage, "/World/object_mesh_test2")

            vertices = [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (0.0, 1.0, 0.0),
                (2.0, 1.0, 0.0),
                (2.0, 2.0, 0.0),
                (1.0, 2.0, 0.0),
            ]

            face_indices = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4]]

            subset_indices = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4]]

            mtl_path = omni.usd.get_stage_next_free_path(stage, "/World/Looks/TestMaterial", False)
            mat_prim = stage.DefinePrim(mtl_path, "Material")
            material_prim = UsdShade.Material.Get(stage, mat_prim.GetPath())

            mesh_prims = [
                await self._create_test_mesh(
                    stage,
                    "/World/object_subset_test/QuadMesh",
                    vertices,
                    face_indices,
                    subset_indices,
                    material_binding=material_prim,
                ),
                await self._create_test_mesh(stage, "/World/object_mesh_test/QuadMesh", vertices, [face_indices[0]]),
                await self._create_test_mesh(
                    stage,
                    "/World/object_mesh_test2/QuadMesh",
                    vertices,
                    [face_indices[0]],
                    material_binding=material_prim,
                ),
            ]

            return stage, mesh_prims

        async def create(self):
            self.stage, self.mesh_prims = await self._create_test_stage()

        async def destroy(self):
            if self.stage is not None:
                await omni.usd.get_context(self._context_name).close_stage_async()
            self.stage = None
            self.mesh_prims = []

        def __init__(self, context_name: str):
            self._context_name = context_name
            self.mesh_prims = []
            self.stage = None

    async def test_check_default_material_should_skip_check(self):
        # Arrange
        default_material = DefaultMaterial()

        with patch.object(DefaultMaterial, "on_progress") as progress_mock:
            # Act
            success, message, data = await default_material._check(Mock(), Mock(), [])

        # Assert
        self.assertTrue(success)
        self.assertEqual("Check:\n- SKIPPED: No selected prims", message)
        self.assertIsNone(data)

        self.assertEqual(1, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args)

    async def test_fix_default_material_should_quick_return_success(self):
        # Arrange
        default_material = DefaultMaterial()

        with patch.object(DefaultMaterial, "on_progress") as progress_mock:
            # Act
            success, message, data = await default_material._fix(Mock(), Mock(), [])

        # Assert
        self.assertTrue(success)
        self.assertEqual("Fix:\n", message)
        self.assertIsNone(data)

        self.assertEqual(1, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args)

    async def test_check_default_material_should_work_correctly(self):
        # Arrange
        default_material = DefaultMaterial()
        env, schema = await self._setup()

        with patch.object(DefaultMaterial, "on_progress") as progress_mock:
            # Act
            success, message, data = await default_material._check(schema, schema.context_name, env.mesh_prims)
        await self._cleanup(env, schema)

        # Assert
        self.assertFalse(success)
        self.assertIsNone(data)

        expected_message = (
            "Check:\n- CHECK: /World/object_subset_test/QuadMesh/subset1\n"
            "- CHECK: /World/object_subset_test/QuadMesh/subset2\n"
            "- CHECK: /World/object_mesh_test/QuadMesh\n"
            "- OK: /World/object_mesh_test2/QuadMesh\n"
        )
        self.assertEqual(message, expected_message)

        self.assertEqual(4, progress_mock.call_count)
        self.assertEqual(call(1.0, "- OK: /World/object_mesh_test2/QuadMesh\n", False), progress_mock.call_args)

    async def _cleanup(self, env, schema):
        await env.destroy()
        omni.usd.destroy_context(schema.context_name)

    async def test_fix_default_material_should_work_correctly(self):
        # Arrange
        default_material = DefaultMaterial()
        env, schema = await self._setup()

        with patch.object(DefaultMaterial, "on_progress") as progress_mock:
            # Act
            success, message, data = await default_material._fix(schema, schema.context_name, env.mesh_prims)
        await self._cleanup(env, schema)

        # Assert
        self.assertTrue(success)
        self.assertIsNone(data)

        expected_message = (
            "Fix:\n- FIXED: /World/object_subset_test/QuadMesh/subset1\n"
            "- FIXED: /World/object_subset_test/QuadMesh/subset2\n"
            "- FIXED: /World/object_mesh_test/QuadMesh\n"
        )
        self.assertEqual(message, expected_message)

        self.assertEqual(4, progress_mock.call_count)
        self.assertEqual(call(1.0, "", True), progress_mock.call_args)

    async def _setup(self):
        schema = DefaultMaterial.Data()
        schema.context_name = "test"
        omni.usd.create_context(schema.context_name)
        env = self.TestStage(schema.context_name)
        await env.create()
        return env, schema
