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

import omni.kit.test
from omni.flux.stage_manager.factory import StageManagerItem

from ... import mesh_prims
from ...mesh_prims import MeshPrimsFilterPlugin

__all__ = ["TestMeshPrimsFilterUnit"]

_HASH = "0123456789ABCDEF"


class TestMeshPrimsFilterUnit(omni.kit.test.AsyncTestCase):
    """Tests Mesh filter predicates against their documented contract."""

    async def test_filter_predicate_with_groupable_mesh_candidates_retains_only_valid_group_rows(self):
        """Retain direct and source-stage-mapped mesh-group candidates."""
        cases = [
            ("mesh_prototype", f"/RootNode/meshes/mesh_{_HASH}/Mesh", "prototype", None, True, True),
            ("empty_mesh_root", f"/RootNode/meshes/mesh_{_HASH}", "empty", None, True, True),
            ("non_instance", "/RootNode/Unrelated", "non_instance", None, True, False),
            (
                "light_group_instance",
                f"/RootNode/lights/light_{_HASH}_0/Mesh",
                "light_instance",
                None,
                True,
                False,
            ),
            (
                "instance_without_instances",
                f"/RootNode/instances/inst_{_HASH}_0/Mesh",
                "instance",
                None,
                False,
                False,
            ),
            (
                "instance_mapped_to_prototype",
                f"/RootNode/instances/inst_{_HASH}_0/Mesh",
                "instance",
                "prototype",
                True,
                True,
            ),
            (
                "instance_mapped_to_empty_mesh_root",
                f"/RootNode/instances/inst_{_HASH}_0/Mesh",
                "instance",
                "empty",
                True,
                True,
            ),
            (
                "instance_mapped_to_missing_prim",
                f"/RootNode/instances/inst_{_HASH}_0/Mesh",
                "instance",
                "missing",
                True,
                False,
            ),
            (
                "instance_mapped_to_invalid_group_candidate",
                f"/RootNode/instances/inst_{_HASH}_0/Mesh",
                "instance",
                "invalid",
                True,
                False,
            ),
        ]
        expected_mesh_path = f"/RootNode/meshes/mesh_{_HASH}/Mesh"

        for title, prim_path, source_kind, mapped_kind, include_instances, expected in cases:
            with self.subTest(title=title):
                # Arrange
                prim = MagicMock()
                prim.__bool__.return_value = True
                prim.GetPath.return_value = prim_path
                mapped_prim = MagicMock()
                mapped_prim.__bool__.return_value = mapped_kind not in {None, "missing"}
                mapped_prim.GetPath.return_value = expected_mesh_path
                item = StageManagerItem(prim_path, data=prim)
                plugin = MeshPrimsFilterPlugin(include_instances=include_instances)
                with (
                    patch.object(mesh_prims, "get_prototype") as get_prototype_mock,
                    patch.object(mesh_prims, "is_mesh_prototype") as is_mesh_prototype_mock,
                    patch.object(mesh_prims, "is_empty_mesh_prim") as is_empty_mesh_prim_mock,
                    patch.object(mesh_prims, "is_instance") as is_instance_mock,
                    patch.object(mesh_prims, "is_in_light_group") as is_in_light_group_mock,
                ):
                    get_prototype_mock.return_value = None if mapped_kind == "missing" else mapped_prim
                    is_mesh_prototype_mock.side_effect = [
                        source_kind == "prototype",
                        mapped_kind == "prototype",
                    ]
                    is_empty_mesh_prim_mock.side_effect = [source_kind == "empty", mapped_kind == "empty"]
                    is_instance_mock.return_value = source_kind in {"instance", "light_instance"}
                    is_in_light_group_mock.return_value = source_kind == "light_instance"

                    # Act
                    result = plugin.filter_predicate(item)

                    # Assert
                    self.assertEqual(expected, result)
                    with self.assertRaises(RuntimeError):
                        _ = item.prepared_group_memberships
                    if mapped_kind is None:
                        get_prototype_mock.assert_not_called()
                    else:
                        get_prototype_mock.assert_called_once_with(prim)
                        if mapped_kind == "missing":
                            mapped_prim.GetPath.assert_not_called()
                        else:
                            mapped_prim.GetPath.assert_called_once_with()

    async def test_filter_predicate_with_invalid_prim_rejects_without_path_or_stage_access(self):
        """Reject a falsey prim before path, stage, or classification access."""
        # Arrange
        prim = MagicMock()
        prim.__bool__.return_value = False
        item = StageManagerItem("invalid", data=prim)
        plugin = MeshPrimsFilterPlugin()
        with (
            patch.object(mesh_prims, "get_prototype") as get_prototype_mock,
            patch.object(mesh_prims, "is_mesh_prototype") as is_mesh_prototype_mock,
            patch.object(mesh_prims, "is_empty_mesh_prim") as is_empty_mesh_prim_mock,
            patch.object(mesh_prims, "is_instance") as is_instance_mock,
            patch.object(mesh_prims, "is_in_light_group") as is_in_light_group_mock,
        ):
            # Act
            result = plugin.filter_predicate(item)

            # Assert
            self.assertFalse(result)
            prim.GetPath.assert_not_called()
            prim.GetStage.assert_not_called()
            get_prototype_mock.assert_not_called()
            is_mesh_prototype_mock.assert_not_called()
            is_empty_mesh_prim_mock.assert_not_called()
            is_instance_mock.assert_not_called()
            is_in_light_group_mock.assert_not_called()
