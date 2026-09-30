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

__all__ = ("TestAllStageMeshesResolver", "TestSelectedMeshResolver")

import pathlib
from unittest.mock import MagicMock, patch

from omni.kit.test import AsyncTestCase
from pxr import Sdf, Usd

from lightspeed.trex.asset_replacements.core.shared.data_models import AssetReplacementsValidators

from ...enums import MeshReferenceSelection, RemixType
from ...resolvers import (
    AllStageMeshesResolver,
    ConstantResolver,
    ResolverValueError,
    SelectedMeshResolver,
    get_resolver_rule,
)


class TestSelectedMeshResolver(AsyncTestCase):
    """Test mesh resolver choices and selected references."""

    async def test_selected_mesh_without_context_rejects_before_stage_lookup(self):
        """A missing context must not select a stage."""
        # Arrange
        prim = MagicMock()
        resolver = SelectedMeshResolver()
        with patch.object(AssetReplacementsValidators, "get_prim_references") as get_references:
            # Act
            with self.assertRaises(ResolverValueError):
                resolver(prim)

        # Assert
        get_references.assert_not_called()

    async def test_mesh_resolver_catalog(self):
        """Mesh resolver choices preserve order, default to the selected mesh, and pick references per scope."""
        # Arrange
        remix_type = RemixType.MESH_FILE_PATH

        # Act
        rule = get_resolver_rule(remix_type, pathlib.Path)

        # Assert
        self.assertEqual(rule.options, (SelectedMeshResolver, AllStageMeshesResolver, ConstantResolver))
        self.assertEqual(tuple(option.label for option in rule.options), ("Selected Mesh", "All Meshes", "Constant"))
        self.assertIs(rule.default, SelectedMeshResolver)
        self.assertIs(SelectedMeshResolver().reference_selection, MeshReferenceSelection.SELECTED)
        self.assertIs(AllStageMeshesResolver().reference_selection, MeshReferenceSelection.ALL)

    async def test_selected_mesh_resolver_rejects_missing_internal_and_ambiguous_references(self):
        """Mesh inputs require exactly one external model source."""
        for title, references in (
            ("missing", []),
            ("internal", [Sdf.Reference(primPath="/World/Model")]),
            ("ambiguous", [Sdf.Reference("first.usd"), Sdf.Reference("second.usd")]),
        ):
            with self.subTest(title=title):
                # Arrange
                prim = MagicMock()
                layer = MagicMock()
                with (
                    patch.object(
                        AssetReplacementsValidators,
                        "get_prim_references",
                        return_value=(prim, [(reference, layer) for reference in references]),
                    ),
                    patch.object(Sdf, "ComputeAssetPathRelativeToLayer", side_effect=lambda _layer, path: path),
                ):
                    # Act
                    with self.assertRaises(ResolverValueError) as error_context:
                        SelectedMeshResolver(context_name="stagecraft", reference_selection=MeshReferenceSelection.ALL)(
                            prim
                        )

                # Assert
                self.assertIsInstance(error_context.exception, ResolverValueError)

    async def test_selected_mesh_resolver_preserves_composed_reference_url(self):
        """Composed reference resolution keeps an absolute Omniverse URL unchanged."""
        # Arrange
        prim = MagicMock()
        prim.GetPath.return_value = "/World/Robot"
        reference = Sdf.Reference("../models/robot.usd")
        layer = MagicMock()
        resolved_url = "omniverse://server/Projects/Scene/models/robot.usd"

        with (
            patch.object(
                AssetReplacementsValidators,
                "get_prim_references",
                return_value=(None, ((reference, layer),)),
            ) as get_references,
            patch.object(Sdf, "ComputeAssetPathRelativeToLayer", return_value=resolved_url) as compute_path,
        ):
            # Act
            result = SelectedMeshResolver(context_name="stagecraft", reference_selection=MeshReferenceSelection.ALL)(
                prim
            )

        # Assert
        self.assertEqual(result, resolved_url)
        self.assertIs(type(result), str)
        get_references.assert_called_once_with("/World/Robot", "stagecraft")
        compute_path.assert_called_once_with(layer, reference.assetPath)


class TestAllStageMeshesResolver(AsyncTestCase):
    """Test mesh expansion and accepted values."""

    async def test_all_stage_meshes_expand_external_references(self):
        """Expansion includes external references and excludes internal or absent references."""
        # Arrange
        stage = MagicMock()
        layer = MagicMock()
        prims = []
        for path in ("/World", "/World/External", "/World/Internal", "/World/Mixed", "/World/Empty"):
            prim = MagicMock()
            prim.GetPath.return_value = path
            prims.append(prim)
        references = {
            "/World/External": [(Sdf.Reference("model.usd"), layer)],
            "/World/Internal": [(Sdf.Reference(primPath="/World/Empty"), layer)],
            "/World/Mixed": [
                (Sdf.Reference(primPath="/World/Empty"), layer),
                (Sdf.Reference("other.usd"), layer),
            ],
        }
        resolver = AllStageMeshesResolver(context_name="stagecraft")
        with (
            patch.object(Usd, "TraverseInstanceProxies"),
            patch.object(Usd.PrimRange, "Stage", return_value=prims),
            patch.object(
                AssetReplacementsValidators,
                "get_prim_references",
                side_effect=lambda path, _context, *, stage, ancestor_cache: (None, references.get(path, [])),
            ),
        ):
            # Act
            paths = list(resolver.iter_stage_prim_paths(stage))

        # Assert
        self.assertEqual(paths, ["/World/External", "/World/Mixed"])

    async def test_all_stage_meshes_accepts_resolved_value(self):
        """The resolver accepts an external model path."""
        # Arrange
        resolver = AllStageMeshesResolver(context_name="stagecraft")

        # Act
        accepted = resolver.accepts_resolved_value("model.usd")

        # Assert
        self.assertTrue(accepted)
