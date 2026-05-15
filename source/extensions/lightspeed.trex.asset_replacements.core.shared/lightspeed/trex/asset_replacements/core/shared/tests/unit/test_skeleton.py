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

from unittest.mock import MagicMock, patch

from lightspeed.trex.asset_replacements.core.shared import skeleton as _skeleton
from omni.kit.test import AsyncTestCase
from pxr import Gf, Sdf, Usd, UsdGeom, UsdSkel


class TestSkeleton(AsyncTestCase):
    @staticmethod
    def _scaled_matrix(scale: float) -> Gf.Matrix4d:
        return Gf.Matrix4d(
            scale,
            0,
            0,
            0,
            0,
            scale,
            0,
            0,
            0,
            0,
            scale,
            0,
            0,
            0,
            0,
            1,
        )

    @staticmethod
    def _nonuniform_matrix() -> Gf.Matrix4d:
        return Gf.Matrix4d(
            100,
            0,
            0,
            0,
            0,
            120,
            0,
            0,
            0,
            0,
            100,
            0,
            0,
            0,
            0,
            1,
        )

    @staticmethod
    def _translated_scaled_matrix(scale: float) -> Gf.Matrix4d:
        return Gf.Matrix4d(
            scale,
            0,
            0,
            0,
            0,
            scale,
            0,
            0,
            0,
            0,
            scale,
            0,
            400,
            500,
            600,
            1,
        )

    @staticmethod
    def _define_bound_mesh(
        stage: Usd.Stage,
        mesh_path: str,
        geom_bind_matrix: Gf.Matrix4d | None = None,
        skeleton_path: str = "/RootNode/meshes/mesh_CAPTURED/skel",
    ) -> tuple[Usd.Prim, UsdSkel.BindingAPI]:
        skeleton = UsdSkel.Skeleton.Define(stage, skeleton_path)
        mesh = UsdGeom.Mesh.Define(stage, mesh_path).GetPrim()
        binding_api = UsdSkel.BindingAPI.Apply(mesh)
        binding_api.CreateSkeletonRel().SetTargets([skeleton.GetPrim().GetPath()])
        if geom_bind_matrix is not None:
            binding_api.CreateGeomBindTransformAttr(geom_bind_matrix)
        return mesh, binding_api

    @staticmethod
    def _define_skeleton_binding_stage(
        apply_binding: bool = True,
    ) -> tuple[Usd.Stage, Usd.Prim, UsdSkel.Skeleton, Usd.Prim]:
        stage = Usd.Stage.CreateInMemory()
        skel_root = UsdSkel.Root.Define(stage, "/RootNode/meshes/mesh_CAPTURED").GetPrim()
        skeleton = UsdSkel.Skeleton.Define(stage, "/RootNode/meshes/mesh_CAPTURED/skel")
        mesh = UsdGeom.Mesh.Define(stage, "/RootNode/meshes/mesh_CAPTURED/ref_test/replacement_mesh").GetPrim()
        if apply_binding:
            binding_api = UsdSkel.BindingAPI.Apply(mesh)
            binding_api.CreateSkeletonRel().SetTargets([skeleton.GetPrim().GetPath()])
        return stage, skel_root, skeleton, mesh

    @staticmethod
    def _mock_attr(value, path: str):
        attr = MagicMock()
        attr.Get.return_value = value
        attr.GetPath.return_value = Sdf.Path(path)
        return attr

    @classmethod
    def _make_binding_model(
        cls,
        *,
        captured_joints: list[str] | None = None,
        mesh_joints: list[str] | None = None,
        remapped_joints: list[str] | None = None,
        original_joints: list[str] | None = None,
        original_indices: list[int] | None = None,
        current_indices: list[int] | None = None,
    ):
        binding = _skeleton.SkeletonReplacementBinding.__new__(_skeleton.SkeletonReplacementBinding)
        binding._stage = "test_context"

        binding._captured_skeleton = MagicMock()
        binding._captured_skeleton.GetJointsAttr.return_value.Get.return_value = captured_joints or []

        original_skeleton = MagicMock()
        original_skeleton.GetJointsAttr.return_value.Get.return_value = mesh_joints or []

        original_indices_attr = cls._mock_attr(original_indices, "/RootNode/meshes/mesh.primvars:skel:jointIndices")
        binding._orig_binding_api = MagicMock()
        binding._orig_binding_api.GetSkeleton.return_value = original_skeleton
        binding._orig_binding_api.GetJointIndicesPrimvar.return_value = (
            original_indices_attr if original_indices is not None else None
        )

        remix_attr = cls._mock_attr(remapped_joints, "/RootNode/meshes/mesh.skel:remix_joints")
        original_joints_attr = cls._mock_attr(original_joints, "/RootNode/meshes/mesh.skel:joints")
        binding._bound_prim = MagicMock()
        binding._bound_prim.GetAttribute.side_effect = lambda attr_name: (
            remix_attr if attr_name == _skeleton.SkeletonReplacementBinding.REMIX_JOINT_ATTR else None
        )

        binding._orig_bound_prim = MagicMock()
        binding._orig_bound_prim.GetAttribute.side_effect = lambda attr_name: (
            original_joints_attr if attr_name == _skeleton.SkeletonReplacementBinding.JOINT_ATTR else None
        )

        joint_indices_attr = cls._mock_attr(current_indices, "/RootNode/meshes/mesh.primvars:skel:jointIndices")
        joints_attr = cls._mock_attr(["old_joint"], "/RootNode/meshes/mesh.skel:joints")
        binding._binding_api = MagicMock()
        binding._binding_api.GetPrim.return_value.GetAttribute.return_value = remix_attr
        binding._binding_api.GetJointIndicesAttr.return_value = joint_indices_attr
        binding._binding_api.GetJointsAttr.return_value = joints_attr

        binding._original_mesh_joint_indices = None
        return binding

    async def test_path_names_only_returns_last_path_components(self):
        # Arrange
        paths = ["/Root/Armature/Hips", "/Root/Armature/Spine"]

        # Act
        result = _skeleton.path_names_only(paths)

        # Assert
        self.assertEqual(result, ["Hips", "Spine"])

    async def test_clear_skel_root_type_with_skel_root_should_author_xform(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        prim = UsdSkel.Root.Define(stage, "/RootNode/meshes/skelroot").GetPrim()

        with patch.object(_skeleton.omni.kit.commands, "execute") as execute_mock:
            # Act
            result = _skeleton.clear_skel_root_type(prim)

        # Assert
        self.assertTrue(result)
        execute_mock.assert_called_once_with("SetPrimTypeName", prim=prim, type_name="Xform")

    async def test_clear_skel_root_type_with_non_skel_root_should_return_false(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        prim = UsdGeom.Xform.Define(stage, "/RootNode/meshes/not_skelroot").GetPrim()

        with patch.object(_skeleton.omni.kit.commands, "execute") as execute_mock:
            # Act
            result = _skeleton.clear_skel_root_type(prim)

        # Assert
        self.assertFalse(result)
        execute_mock.assert_not_called()

    async def test_author_binding_to_skel_should_set_binding_target(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        skeleton = UsdSkel.Skeleton.Define(stage, "/RootNode/meshes/mesh_CAPTURED/skel")
        mesh = UsdGeom.Mesh.Define(stage, "/RootNode/meshes/mesh_CAPTURED/ref_test/replacement_mesh").GetPrim()
        binding_api = UsdSkel.BindingAPI.Apply(mesh)
        skeleton_rel = binding_api.CreateSkeletonRel()

        with patch.object(_skeleton.omni.kit.commands, "execute") as execute_mock:
            # Act
            _skeleton.author_binding_to_skel(binding_api, skeleton.GetPrim())

        # Assert
        execute_mock.assert_called_once_with(
            "SetRelationshipTargetsCommand",
            relationship=skeleton_rel,
            targets=[skeleton.GetPrim().GetPath()],
        )

    async def test_repair_skinned_replacement_scale_without_prim_should_return_zero(self):
        # Arrange
        prim = None

        # Act
        result = _skeleton.repair_skinned_replacement_scale(prim)

        # Assert
        self.assertEqual(result, 0)

    async def test_repair_skinned_replacement_scale_without_geom_bind_attr_should_skip_mesh(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        mesh, _ = self._define_bound_mesh(stage, "/RootNode/meshes/mesh_CAPTURED/ref_test/replacement_mesh")

        # Act
        result = _skeleton.repair_skinned_replacement_scale(mesh)

        # Assert
        self.assertEqual(result, 0)

    async def test_repair_skinned_replacement_scale_with_non_large_geom_bind_scale_should_skip_mesh(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        mesh, binding_api = self._define_bound_mesh(
            stage,
            "/RootNode/meshes/mesh_CAPTURED/ref_test/replacement_mesh",
            self._scaled_matrix(2),
        )

        # Act
        result = _skeleton.repair_skinned_replacement_scale(mesh)

        # Assert
        self.assertEqual(result, 0)
        self.assertAlmostEqual(binding_api.GetGeomBindTransformAttr().Get()[0][0], 2)

    async def test_repair_skinned_replacement_scale_with_nonuniform_geom_bind_scale_should_skip_mesh(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        mesh, binding_api = self._define_bound_mesh(
            stage,
            "/RootNode/meshes/mesh_CAPTURED/ref_test/replacement_mesh",
            self._nonuniform_matrix(),
        )

        # Act
        result = _skeleton.repair_skinned_replacement_scale(mesh)

        # Assert
        self.assertEqual(result, 0)
        self.assertAlmostEqual(binding_api.GetGeomBindTransformAttr().Get()[1][1], 120)

    async def test_repair_skinned_replacement_scale_should_author_geom_bind_to_edit_target_only(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        source_layer = Sdf.Layer.CreateAnonymous("source_layer")
        stage.GetRootLayer().subLayerPaths.append(source_layer.identifier)
        with Usd.EditContext(stage, source_layer):
            mesh, binding_api = self._define_bound_mesh(
                stage,
                "/RootNode/meshes/mesh_CAPTURED/ref_test/replacement_mesh",
                self._scaled_matrix(100),
            )
        attr_path = binding_api.GetGeomBindTransformAttr().GetPath()
        stage.SetEditTarget(stage.GetRootLayer())

        # Act
        result = _skeleton.repair_skinned_replacement_scale(mesh)

        # Assert
        self.assertEqual(result, 1)
        self.assertAlmostEqual(binding_api.GetGeomBindTransformAttr().Get()[0][0], 1)
        self.assertAlmostEqual(source_layer.GetAttributeAtPath(attr_path).default[0][0], 100)
        self.assertAlmostEqual(stage.GetRootLayer().GetAttributeAtPath(attr_path).default[0][0], 1)
        self.assertIsNone(stage.GetSessionLayer().GetAttributeAtPath(attr_path))

    async def test_repair_skinned_replacement_scale_should_only_repair_selected_bound_mesh(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        selected_mesh, selected_binding_api = self._define_bound_mesh(
            stage,
            "/RootNode/meshes/mesh_CAPTURED/ref_selected/replacement_mesh",
            self._scaled_matrix(100),
        )
        _, skipped_binding_api = self._define_bound_mesh(
            stage,
            "/RootNode/meshes/mesh_CAPTURED/ref_other/replacement_mesh",
            self._scaled_matrix(100),
        )

        # Act
        result = _skeleton.repair_skinned_replacement_scale(selected_mesh)

        # Assert
        self.assertEqual(result, 1)
        self.assertAlmostEqual(selected_binding_api.GetGeomBindTransformAttr().Get()[0][0], 1)
        self.assertAlmostEqual(skipped_binding_api.GetGeomBindTransformAttr().Get()[0][0], 100)

    async def test_repair_skinned_replacement_scale_should_repair_nearby_replacement_skeleton(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        skeleton = UsdSkel.Skeleton.Define(
            stage,
            "/RootNode/meshes/mesh_CAPTURED/ref_test/XForms/World/replacement_skeleton/Skeleton",
        )
        rest_attr = skeleton.CreateRestTransformsAttr([self._scaled_matrix(100), Gf.Matrix4d(1)])
        bind_attr = skeleton.CreateBindTransformsAttr([self._scaled_matrix(100), self._translated_scaled_matrix(100)])
        mesh, binding_api = self._define_bound_mesh(
            stage,
            "/RootNode/meshes/mesh_CAPTURED/ref_test/XForms/World/replacement_skeleton/replacement_mesh",
            self._scaled_matrix(100),
        )

        # Act
        result = _skeleton.repair_skinned_replacement_scale(mesh)

        # Assert
        self.assertEqual(result, 3)
        self.assertAlmostEqual(binding_api.GetGeomBindTransformAttr().Get()[0][0], 1)
        self.assertAlmostEqual(rest_attr.Get()[0][0][0], 1)
        self.assertAlmostEqual(rest_attr.Get()[1][0][0], 1)
        self.assertAlmostEqual(bind_attr.Get()[0][0][0], 1)
        self.assertAlmostEqual(bind_attr.Get()[1][3][0], 4)
        self.assertAlmostEqual(bind_attr.Get()[1][3][1], 5)
        self.assertAlmostEqual(bind_attr.Get()[1][3][2], 6)

    async def test_repair_skinned_replacement_scale_skips_skeleton_targeted_by_active_binding(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        skeleton = UsdSkel.Skeleton.Define(
            stage,
            "/RootNode/meshes/mesh_CAPTURED/ref_test/XForms/World/replacement_skeleton/Skeleton",
        )
        rest_attr = skeleton.CreateRestTransformsAttr([self._scaled_matrix(100)])
        skeleton.CreateBindTransformsAttr([self._translated_scaled_matrix(100)])
        mesh, binding_api = self._define_bound_mesh(
            stage,
            "/RootNode/meshes/mesh_CAPTURED/ref_test/XForms/World/replacement_skeleton/replacement_mesh",
            self._scaled_matrix(100),
        )
        active_mesh = UsdGeom.Mesh.Define(
            stage,
            "/RootNode/meshes/mesh_CAPTURED/ref_test/XForms/World/replacement_skeleton/active_mesh",
        ).GetPrim()
        UsdSkel.BindingAPI.Apply(active_mesh).CreateSkeletonRel().SetTargets([skeleton.GetPrim().GetPath()])

        # Act
        result = _skeleton.repair_skinned_replacement_scale(mesh)

        # Assert
        self.assertEqual(result, 1)
        self.assertAlmostEqual(binding_api.GetGeomBindTransformAttr().Get()[0][0], 1)
        self.assertAlmostEqual(rest_attr.Get()[0][0][0], 100)

    async def test_repair_skinned_replacement_scale_skips_skeleton_attrs_with_mismatched_scale(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        skeleton = UsdSkel.Skeleton.Define(
            stage,
            "/RootNode/meshes/mesh_CAPTURED/ref_test/XForms/World/replacement_skeleton/Skeleton",
        )
        rest_attr = skeleton.CreateRestTransformsAttr([self._scaled_matrix(50)])
        mesh, binding_api = self._define_bound_mesh(
            stage,
            "/RootNode/meshes/mesh_CAPTURED/ref_test/XForms/World/replacement_skeleton/replacement_mesh",
            self._scaled_matrix(100),
        )

        # Act
        result = _skeleton.repair_skinned_replacement_scale(mesh)

        # Assert
        self.assertEqual(result, 1)
        self.assertAlmostEqual(binding_api.GetGeomBindTransformAttr().Get()[0][0], 1)
        self.assertAlmostEqual(rest_attr.Get()[0][0][0], 50)

    async def test_targets_captured_skeleton_without_skeleton_relationship_should_return_false(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        mesh = UsdGeom.Mesh.Define(stage, "/RootNode/meshes/mesh_CAPTURED/ref_test/replacement_mesh").GetPrim()
        binding_api = UsdSkel.BindingAPI.Apply(mesh)

        # Act
        result = _skeleton._targets_captured_skeleton(binding_api)

        # Assert
        self.assertFalse(result)

    async def test_uniform_basis_scale_with_zero_basis_should_return_none(self):
        # Arrange
        matrix = Gf.Matrix4d()

        # Act
        result = _skeleton._uniform_basis_scale(matrix)

        # Assert
        self.assertIsNone(result)

    async def test_matrix_array_with_invalid_matrix_value_should_return_none(self):
        # Arrange
        matrices = ["invalid matrix"]

        # Act
        result = _skeleton._matrix_array_with_normalized_uniform_basis(matrices, 100, False)

        # Assert
        self.assertIsNone(result)

    async def test_skeleton_replacement_binding_with_valid_capture_binding_should_initialize_from_bound_prim(self):
        # Arrange
        stage, skel_root, skeleton, mesh = self._define_skeleton_binding_stage()

        with patch.object(_skeleton.carb, "log_warn") as log_warn_mock:
            # Act
            binding = _skeleton.SkeletonReplacementBinding(skel_root, mesh)

        # Assert
        self.assertTrue(stage)
        self.assertEqual(binding.bound_prim, mesh)
        self.assertEqual(binding.captured_skeleton.GetPrim().GetPath(), skeleton.GetPrim().GetPath())
        self.assertEqual(binding.original_skeleton.GetPrim().GetPath(), skeleton.GetPrim().GetPath())
        log_warn_mock.assert_called_once()

    async def test_skeleton_replacement_binding_with_non_skel_root_should_raise_definition_error(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        skel_root = UsdGeom.Xform.Define(stage, "/RootNode/meshes/mesh_CAPTURED").GetPrim()
        mesh = UsdGeom.Mesh.Define(stage, "/RootNode/meshes/mesh_CAPTURED/ref_test/replacement_mesh").GetPrim()

        # Act
        with self.assertRaises(_skeleton.SkeletonDefinitionError) as cm:
            _skeleton.SkeletonReplacementBinding(skel_root, mesh)

        # Assert
        self.assertIn("Skeleton root is not valid", str(cm.exception))

    async def test_skeleton_replacement_binding_without_captured_skeleton_should_raise_definition_error(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        skel_root = UsdSkel.Root.Define(stage, "/RootNode/meshes/mesh_CAPTURED").GetPrim()
        mesh = UsdGeom.Mesh.Define(stage, "/RootNode/meshes/mesh_CAPTURED/ref_test/replacement_mesh").GetPrim()

        # Act
        with self.assertRaises(_skeleton.SkeletonDefinitionError) as cm:
            _skeleton.SkeletonReplacementBinding(skel_root, mesh)

        # Assert
        self.assertIn("Captured skeleton not found", str(cm.exception))

    async def test_skeleton_replacement_binding_without_bound_binding_should_raise_definition_error(self):
        # Arrange
        stage, skel_root, _, mesh = self._define_skeleton_binding_stage(apply_binding=False)

        # Act
        with self.assertRaises(_skeleton.SkeletonDefinitionError) as cm:
            _skeleton.SkeletonReplacementBinding(skel_root, mesh)

        # Assert
        self.assertTrue(stage)
        self.assertIn("No skel binding found", str(cm.exception))

    async def test_generate_joint_map_with_matching_joint_names_should_return_indices(self):
        # Arrange
        mesh_joints = ["/Replacement/Hips", "/Replacement/Spine"]
        captured_joints = ["/Captured/Spine", "/Captured/Hips"]

        # Act
        result = _skeleton.SkeletonReplacementBinding.generate_joint_map(mesh_joints, captured_joints)

        # Assert
        self.assertEqual(result, [1, 0])

    async def test_generate_joint_map_with_missing_joint_and_fallback_should_return_index_order(self):
        # Arrange
        mesh_joints = ["/Replacement/Hips", "/Replacement/Unknown", "/Replacement/Hand"]
        captured_joints = ["/Captured/Hips"]

        # Act
        result = _skeleton.SkeletonReplacementBinding.generate_joint_map(mesh_joints, captured_joints, fallback=True)

        # Assert
        self.assertEqual(result, [0, 0, 0])

    async def test_generate_joint_map_with_missing_joint_without_fallback_should_raise_error(self):
        # Arrange
        mesh_joints = ["/Replacement/Hips", "/Replacement/Unknown"]
        captured_joints = ["/Captured/Hips"]

        with patch.object(_skeleton.carb, "log_error") as log_error_mock:
            # Act
            with self.assertRaises(_skeleton.SkeletonAutoRemappingError) as cm:
                _skeleton.SkeletonReplacementBinding.generate_joint_map(mesh_joints, captured_joints)

        # Assert
        self.assertEqual(str(cm.exception), "No valid remapping found using joint names.")
        log_error_mock.assert_called_once()

    async def test_get_captured_joints_should_return_captured_skeleton_joints(self):
        # Arrange
        binding = self._make_binding_model(captured_joints=["Hips", "Spine"])

        # Act
        result = binding.get_captured_joints()

        # Assert
        self.assertEqual(result, ["Hips", "Spine"])

    async def test_get_mesh_joints_should_return_original_skeleton_joints(self):
        # Arrange
        binding = self._make_binding_model(mesh_joints=["MeshHips", "MeshSpine"])

        # Act
        result = binding.get_mesh_joints()

        # Assert
        self.assertEqual(result, ["MeshHips", "MeshSpine"])

    async def test_get_remapped_joints_with_remix_attr_should_return_remix_joints(self):
        # Arrange
        binding = self._make_binding_model(remapped_joints=["Hips", "Spine"], original_joints=["OldHips"])

        # Act
        result = binding.get_remapped_joints()

        # Assert
        self.assertEqual(result, ["Hips", "Spine"])

    async def test_get_remapped_joints_without_remix_attr_should_return_original_joints(self):
        # Arrange
        binding = self._make_binding_model(remapped_joints=None, original_joints=["OldHips", "OldSpine"])

        # Act
        result = binding.get_remapped_joints()

        # Assert
        self.assertEqual(result, ["OldHips", "OldSpine"])

    async def test_get_remapped_joints_without_authored_values_should_return_empty_list(self):
        # Arrange
        binding = self._make_binding_model(remapped_joints=None, original_joints=None)

        # Act
        result = binding.get_remapped_joints()

        # Assert
        self.assertEqual(result, [])

    async def test_get_joint_map_should_map_missing_joints_to_negative_one(self):
        # Arrange
        binding = self._make_binding_model(captured_joints=["Hips"], remapped_joints=["Hips", "Missing"])

        # Act
        result = binding.get_joint_map()

        # Assert
        self.assertEqual(result, [0, -1])

    async def test_get_original_joint_indices_should_cache_original_primvar(self):
        # Arrange
        binding = self._make_binding_model(original_indices=[0, 1, 0])

        # Act
        result = binding.get_original_joint_indices()

        # Assert
        self.assertEqual(result, [0, 1, 0])
        self.assertEqual(binding._original_mesh_joint_indices, [0, 1, 0])

    async def test_get_original_joint_indices_with_cached_value_should_return_cached_value(self):
        # Arrange
        binding = self._make_binding_model(original_indices=[0, 1, 0])
        binding._original_mesh_joint_indices = [1, 1, 0]

        # Act
        result = binding.get_original_joint_indices()

        # Assert
        self.assertEqual(result, [1, 1, 0])
        binding._orig_binding_api.GetJointIndicesPrimvar.assert_not_called()

    async def test_get_joint_indices_should_return_current_joint_indices(self):
        # Arrange
        binding = self._make_binding_model(current_indices=[1, 0, 1])

        # Act
        result = binding.get_joint_indices()

        # Assert
        self.assertEqual(result, [1, 0, 1])

    async def test_repair_scale_should_repair_bound_prim(self):
        # Arrange
        binding = self._make_binding_model()

        with patch.object(_skeleton, "repair_skinned_replacement_scale", return_value=4) as repair_mock:
            # Act
            result = binding.repair_scale()

        # Assert
        self.assertEqual(result, 4)
        repair_mock.assert_called_once_with(binding._bound_prim)

    async def test_apply_with_joint_map_should_author_remapped_joints_indices_and_clear_old_joints(self):
        # Arrange
        binding = self._make_binding_model(captured_joints=["Hips", "Spine"], original_indices=[0, 1, 0])
        binding.repair_scale = MagicMock(return_value=2)

        with patch.object(_skeleton.omni.kit.commands, "execute") as execute_mock:
            # Act
            result = binding.apply([1, 0])

        # Assert
        self.assertEqual(result, 2)
        binding.repair_scale.assert_called_once_with()
        command_names = [call.args[0] for call in execute_mock.call_args_list]
        self.assertEqual(command_names, ["ChangePropertyCommand", "ChangePropertyCommand", "ChangePropertyCommand"])
        self.assertEqual(execute_mock.call_args_list[0].kwargs["value"], ["Spine", "Hips"])
        self.assertEqual(execute_mock.call_args_list[1].kwargs["value"], [1, 0, 1])
        self.assertIsInstance(execute_mock.call_args_list[2].kwargs["value"], Sdf.ValueBlock)

    async def test_apply_with_empty_original_indices_should_skip_joint_index_authoring(self):
        # Arrange
        binding = self._make_binding_model(captured_joints=["Hips", "Spine"], original_indices=[])
        binding.repair_scale = MagicMock(return_value=1)

        with patch.object(_skeleton.omni.kit.commands, "execute") as execute_mock:
            # Act
            result = binding.apply([1, 0])

        # Assert
        self.assertEqual(result, 1)
        binding.repair_scale.assert_called_once_with()
        command_names = [call.args[0] for call in execute_mock.call_args_list]
        self.assertEqual(command_names, ["ChangePropertyCommand", "ChangePropertyCommand"])

    async def test_cached_replacement_skeletons_get_with_missing_entry_should_return_none(self):
        # Arrange
        cache = _skeleton.CachedReplacementSkeletons()

        # Act
        result = cache.get_skel_replacement("skel_root", "replacement_asset_root")

        # Assert
        self.assertIsNone(result)

    async def test_cached_replacement_skeletons_add_should_cache_new_binding(self):
        # Arrange
        cache = _skeleton.CachedReplacementSkeletons()
        expected_binding = object()

        with patch.object(_skeleton, "SkeletonReplacementBinding", return_value=expected_binding) as binding_mock:
            # Act
            result = cache.add_skel_replacement("skel_root", "replacement_asset_root")

        # Assert
        self.assertIs(result, expected_binding)
        self.assertIs(cache.get_skel_replacement("skel_root", "replacement_asset_root"), expected_binding)
        binding_mock.assert_called_once_with("skel_root", "replacement_asset_root")

    async def test_cached_replacement_skeletons_add_with_existing_binding_should_return_existing_binding(self):
        # Arrange
        cache = _skeleton.CachedReplacementSkeletons()
        expected_binding = object()
        cache._replacement_skel_models[("skel_root", "replacement_asset_root")] = expected_binding

        with patch.object(_skeleton, "SkeletonReplacementBinding") as binding_mock:
            # Act
            result = cache.add_skel_replacement("skel_root", "replacement_asset_root")

        # Assert
        self.assertIs(result, expected_binding)
        binding_mock.assert_not_called()

    async def test_cached_replacement_skeletons_add_with_invalid_binding_should_return_none(self):
        # Arrange
        cache = _skeleton.CachedReplacementSkeletons()

        with patch.object(
            _skeleton,
            "SkeletonReplacementBinding",
            side_effect=_skeleton.SkeletonDefinitionError("invalid skeleton"),
        ):
            # Act
            result = cache.add_skel_replacement("skel_root", "replacement_asset_root")

        # Assert
        self.assertIsNone(result)
