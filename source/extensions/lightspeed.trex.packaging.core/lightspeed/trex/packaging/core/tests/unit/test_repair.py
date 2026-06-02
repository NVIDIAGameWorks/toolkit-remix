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

from pathlib import Path
from unittest.mock import Mock, patch

import omni.kit.test
from lightspeed.trex.packaging.core import PackagingRepairCore
from lightspeed.trex.packaging.core.repair import PackagingRepairRequest
from lightspeed.trex.packaging.core.repair.models import RepairState
from lightspeed.trex.packaging.core.repair.requests import RepairRequestCore, RepairRequestError
from lightspeed.trex.rtxio.core import RtxIoCore
from omni.flux.utils.tests.context_managers import open_test_project
from pxr import Sdf, Usd


class TestPackagingRepairCoreUnit(omni.kit.test.AsyncTestCase):
    async def test_reference_repair_should_update_local_layer(self):
        async with open_test_project("packaging/projects/MainProject/main_project.usda") as project_url:
            project_root = Path(project_url.path).parent
            layer_path = project_root / "broken_refs/broken_refs_all.usda"
            layer = self._layer(layer_path)

            for name, prim_path, missing_asset, replacement_asset in (
                (
                    "remove",
                    "/RootNode/meshes/mesh_ZB98945ABC2E27F5/ref_missing_remove",
                    "missing_remove.usda",
                    None,
                ),
                (
                    "replace",
                    "/RootNode/meshes/mesh_ZB98945ABC2E27F5/ref_missing_replace",
                    "missing_replace.usda",
                    "assets/Cylinder.usda",
                ),
            ):
                with self.subTest(name=name):
                    # Arrange
                    fixed_asset_path = (project_root / replacement_asset).as_posix() if replacement_asset else None
                    item = self._make_item(
                        layer.identifier, prim_path, (layer_path.parent / missing_asset).as_posix(), fixed_asset_path
                    )

                    # Act
                    state = self._apply_repair_requests(layer_path, item)

                    # Assert
                    layer.Reload()
                    references = layer.GetPrimAtPath(prim_path).referenceList.GetAddedOrExplicitItems()
                    self.assertEqual([], state.ignored_items)
                    self.assertEqual(
                        [] if fixed_asset_path is None else [fixed_asset_path],
                        [Path(layer.ComputeAbsolutePath(ref.assetPath)).as_posix() for ref in references],
                    )

    async def test_texture_repair_should_remove_local_texture_opinion(self):
        async with open_test_project("packaging/projects/MainProject/main_project.usda") as project_url:
            # Arrange
            project_root = Path(project_url.path).parent
            layer_path = project_root / "broken_refs/broken_refs_textures.usda"
            layer = self._layer(layer_path)
            attr_path = "/RootNode/PackagingTest/direct_texture/Looks/Mat/Shader.inputs:diffuse_texture"
            item = self._make_item(
                layer.identifier, attr_path, (layer_path.parent / "missing_direct_texture.dds").as_posix()
            )

            # Act
            state = self._apply_repair_requests(layer_path, item)

            # Assert
            layer.Reload()
            self.assertEqual([], state.ignored_items)
            self.assertIsNone(layer.GetPropertyAtPath(attr_path))

    async def test_reference_override_repair_should_report_partial_failure(self):
        # Arrange
        layer_core = Mock()
        reference_core = Mock()
        authoring_core = Mock()
        core = RepairRequestCore(layer_core, reference_core, authoring_core)
        state = RepairState("C:/projects/MainProject/mod.usda", None, use_editable_layer_copies=True)
        request = self._make_item(
            "C:/projects/MainProject/mod.usda",
            "/RootNode/mesh",
            "C:/projects/MainProject/missing.usda",
            "C:/projects/MainProject/replacement.usda",
        )

        layer_core.get_editable_layer.return_value = Mock()
        reference_core.get_reference_group_repair_key.return_value = ("repair-group",)
        authored_references = [
            (Sdf.Path("/RootNode/mesh/ref_a"), Sdf.Reference("missing.usda")),
            (Sdf.Path("/RootNode/mesh/ref_b"), Sdf.Reference("missing.usda")),
        ]
        authoring_core.replace_reference_override.side_effect = [True, False]

        with (
            patch.object(
                core,
                "_resolve_repair_request_data",
                return_value=("C:/projects/MainProject/mod.usda", True, authored_references),
            ),
            patch("lightspeed.trex.packaging.core.repair.requests.carb.log_warn") as log_warn_mock,
            self.assertRaisesRegex(RepairRequestError, "Unable to replace unresolved reference"),
        ):
            # Act
            core.apply_repair_request(state, request)

        # Assert
        self.assertEqual([], state.ignored_items)
        self.assertEqual(
            [(request.layer_identifier, str(request.prim_path), request.asset_path)],
            [(failure.layer_identifier, failure.prim_path, failure.asset_path) for failure in state.failed_repairs],
        )
        self.assertEqual({"c:/projects/mainproject/mod.usda"}, state.dirty_editable_layer_keys)
        self.assertEqual(set(), state.reference_repair_keys)
        log_warn_mock.assert_any_call(
            "Unable to replace unresolved reference 'C:/projects/MainProject/missing.usda' on prim "
            "'/RootNode/mesh/ref_b'"
        )

    async def test_non_usd_reference_repair_should_remove_reference_by_site(self):
        async with open_test_project("packaging/projects/MainProject/main_project.usda") as project_url:
            # Arrange
            project_root = Path(project_url.path).parent
            root_layer = self._layer(project_root / "broken_refs/broken_refs_all.usda")
            unresolved_asset = Path(root_layer.ComputeAbsolutePath("None")).as_posix()

            failed_assets = self._collect_invalid_assets(root_layer, [unresolved_asset])
            self.assertEqual(
                {(root_layer.identifier, "/RootNode/PackagingTest/NoneReference", unresolved_asset)},
                failed_assets,
            )

            # Act
            request = self._make_item(*next(iter(failed_assets)), fixed_asset_path=None)
            state = self._apply_repair_requests(Path(root_layer.identifier), request)

            # Assert
            root_layer.Reload()
            self.assertEqual([], state.ignored_items)
            self.assertEqual(set(), self._collect_invalid_assets(root_layer, [unresolved_asset]))

    async def test_failed_texture_remove_should_report_failed_repair(self):
        async with open_test_project("packaging/projects/MainProject/main_project.usda") as project_url:
            # Arrange
            project_root = Path(project_url.path).parent
            root_layer = self._layer(project_root / "broken_refs/broken_refs_textures.usda")
            texture_path = "/RootNode/PackagingTest/missing_texture_property/Looks/Mat/Shader.inputs:diffuse_texture"
            unresolved_asset = Path(root_layer.ComputeAbsolutePath("./missing_texture.dds")).as_posix()

            # Act
            request = self._make_item(root_layer.identifier, texture_path, unresolved_asset, fixed_asset_path=None)
            state = self._apply_repair_requests(Path(root_layer.identifier), request)

            # Assert
            self.assertEqual([], state.ignored_items)
            self.assertEqual(
                [(root_layer.identifier, texture_path, unresolved_asset)],
                [
                    (
                        failure.layer_identifier,
                        failure.prim_path,
                        failure.asset_path,
                    )
                    for failure in state.failed_repairs
                ],
            )
            self.assertIn("Unable to remove unresolved texture asset", state.failed_repairs[0].message)

    async def test_ignore_action_should_report_ignored_not_failed(self):
        async with open_test_project("packaging/projects/MainProject/main_project.usda") as project_url:
            # Arrange
            project_root = Path(project_url.path).parent
            root_layer = self._layer(project_root / "broken_refs/broken_refs_all.usda")
            unresolved_asset = Path(root_layer.ComputeAbsolutePath("None")).as_posix()

            # Act
            request = self._make_item(
                root_layer.identifier,
                "/RootNode/PackagingTest/NoneReference",
                unresolved_asset,
                fixed_asset_path=unresolved_asset,
            )
            state = self._apply_repair_requests(Path(root_layer.identifier), request)

            # Assert
            self.assertEqual(
                [(root_layer.identifier, "/RootNode/PackagingTest/NoneReference", unresolved_asset)],
                state.ignored_items,
            )
            self.assertEqual([], state.failed_repairs)

    @staticmethod
    def _apply_repair_requests(root_path: Path, item: PackagingRepairRequest):
        core = PackagingRepairCore()
        try:
            return core._apply_repair_requests(str(root_path), [item], use_editable_layer_copies=True)
        finally:
            core.destroy()

    def _layer(self, layer_path: Path) -> Sdf.Layer:
        layer = Sdf.Layer.FindOrOpen(str(layer_path))
        self.assertIsNotNone(layer)
        layer.Reload()
        return layer

    @staticmethod
    def _make_item(layer_identifier: str, prim_path: str, asset_path: str, fixed_asset_path: str | None = None):
        return PackagingRepairRequest(layer_identifier, prim_path, Path(asset_path).as_posix(), fixed_asset_path)

    @staticmethod
    def _collect_invalid_assets(root_layer: Sdf.Layer, unresolved_paths: list[str]) -> set[tuple[str, str, str]]:
        stage = Usd.Stage.Open(root_layer.identifier)
        try:
            return RtxIoCore().collect_invalid_stage_assets(
                list(stage.TraverseAll()),
                unresolved_paths,
                include_missing_authored_textures=False,
            )
        finally:
            stage = None
