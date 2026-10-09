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

__all__ = ["TestAlphaCutoutStageEditsE2E"]

import tempfile
from pathlib import Path

import numpy as np
import omni.client
import omni.kit.undo
import omni.usd
from lightspeed.common import constants
from lightspeed.trex.alpha_cutout.core import (
    MATERIAL_PRIM_NAME,
    AlphaCutoutStageEditor,
    CutMesh,
    MeshCutoutResult,
    read_mesh_source,
    write_cutout_mesh,
    REPLACEMENT_SUFFIX,
    read_mesh_sources,
    resolve_conversion_target,
    write_cutout_replacement,
)
from lightspeed.trex.asset_replacements.core.shared import Setup as AssetReplacementsCore
from lightspeed.trex.utils.common import prim_utils
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit.test import AsyncTestCase
from pxr import Sdf, Usd, UsdGeom, UsdShade

from ..unit.fixtures import write_alpha_texture, write_replacement_file

_RESOURCES_EXT = "lightspeed.trex.app.resources"
_PROJECT = "usd/project_example/combined.usda"
_MESH_PATH = "/RootNode/meshes/mesh_CED45075A077A49A"


def _pass_through_cut_mesh(source) -> CutMesh:
    """Build a cut mesh that keeps the source geometry unchanged."""
    corners = source.triangles.reshape(-1)
    return CutMesh(
        points=source.points[corners],
        triangles=np.arange(corners.shape[0], dtype=np.int32).reshape(-1, 3),
        st=source.st.reshape(-1, 2),
        normals=None if source.normals is None else source.normals.reshape(-1, 3),
    )


def _capture_references(prim: Usd.Prim) -> list[Sdf.Reference]:
    return [
        reference
        for reference, _ in omni.usd.get_composed_references_from_prim(prim, False)
        if constants.MESHES_FOLDER in reference.assetPath
    ]


def _remix_ref_children(prim: Usd.Prim, baseline: set[Sdf.Path] | None = None) -> list[Usd.Prim]:
    """Return the Remix reference children of a prim, excluding the ones listed in the baseline."""
    return [
        child
        for child in prim.GetChildren()
        if child.GetAttribute(constants.IS_REMIX_REF_ATTR).IsValid() and child.GetPath() not in (baseline or set())
    ]


def _baseline(prim: Usd.Prim) -> set[Sdf.Path]:
    return {child.GetPath() for child in _remix_ref_children(prim)}


class TestAlphaCutoutStageEditsE2E(AsyncTestCase):
    """Apply generated cutout files to the example project through the real replacement core."""

    async def _write_cutout(self, stage: Usd.Stage, output_dir: str) -> MeshCutoutResult:
        """Write a pass-through cutout for the fixture mesh and wrap it as a result."""
        source = read_mesh_source(stage, _MESH_PATH)
        self.assertIsNone(source.skip_reason)
        cut_mesh = _pass_through_cut_mesh(source)
        path = write_cutout_mesh(output_dir, source, cut_mesh, stage, True)
        return MeshCutoutResult(source, cut_mesh, 2, 2, 0.0, output_path=path)

    @staticmethod
    def _set_replacement_edit_target(project_url: OmniUrl, stage: Usd.Stage) -> Sdf.Layer:
        layer = Sdf.Layer.FindOrOpen(str(OmniUrl(project_url.parent_url) / "replacements.usda"))
        stage.SetEditTarget(Usd.EditTarget(layer))
        return layer

    async def test_apply_masks_capture_reference_and_references_cutout_on_replacement_layer(self):
        async with open_test_project(_PROJECT, _RESOURCES_EXT) as project_url:
            with tempfile.TemporaryDirectory() as out:
                # Arrange
                context = omni.usd.get_context()
                stage = context.get_stage()
                replacement_layer = self._set_replacement_edit_target(project_url, stage)
                result = await self._write_cutout(stage, out)
                editor = AlphaCutoutStageEditor("")
                self.addCleanup(editor.destroy)
                prim = stage.GetPrimAtPath(_MESH_PATH)
                baseline = _baseline(prim)
                self.assertEqual(len(_capture_references(prim)), 1)

                # Act
                outcomes = editor.apply([result])

                # Assert
                self.assertEqual(len(outcomes), 1)
                self.assertTrue(outcomes[0].reference_added)
                self.assertEqual(_capture_references(prim), [])
                children = _remix_ref_children(prim, baseline)
                self.assertEqual(len(children), 1)
                self.assertEqual(outcomes[0].reference_prim_path, str(children[0].GetPath()))
                spec = replacement_layer.GetPrimAtPath(children[0].GetPath())
                self.assertIsNotNone(spec)
                self.assertTrue(spec.hasReferences)
                cutout_mesh = next(child for child in Usd.PrimRange(children[0]) if child.IsA(UsdGeom.Mesh))
                bound, _ = UsdShade.MaterialBindingAPI(cutout_mesh).ComputeBoundMaterial()
                self.assertEqual(bound.GetPrim().GetName(), MATERIAL_PRIM_NAME)

    async def test_apply_twice_keeps_a_single_reference_child_pointing_at_the_cutout_file(self):
        async with open_test_project(_PROJECT, _RESOURCES_EXT) as project_url:
            with tempfile.TemporaryDirectory() as out:
                # Arrange
                stage = omni.usd.get_context().get_stage()
                self._set_replacement_edit_target(project_url, stage)
                editor = AlphaCutoutStageEditor("")
                self.addCleanup(editor.destroy)
                prim = stage.GetPrimAtPath(_MESH_PATH)
                baseline = _baseline(prim)
                first = await self._write_cutout(stage, out)
                editor.apply([first])
                second = await self._write_cutout(stage, out)

                # Act
                outcomes = editor.apply([second])

                # Assert
                self.assertFalse(outcomes[0].reference_added)
                children = _remix_ref_children(prim, baseline)
                self.assertEqual(len(children), 1)
                references, _ = prim_utils.get_reference_file_paths(prim)
                resolved = {
                    omni.client.normalize_url(layer.ComputeAbsolutePath(reference.assetPath)).lower()
                    for _, reference, layer, _ in references
                }
                self.assertEqual([path for path in resolved if "/cutout_" in path], [second.output_path.lower()])

    async def test_apply_undo_restores_capture_reference_and_removes_reference_child(self):
        async with open_test_project(_PROJECT, _RESOURCES_EXT) as project_url:
            with tempfile.TemporaryDirectory() as out:
                # Arrange
                stage = omni.usd.get_context().get_stage()
                self._set_replacement_edit_target(project_url, stage)
                editor = AlphaCutoutStageEditor("")
                self.addCleanup(editor.destroy)
                prim = stage.GetPrimAtPath(_MESH_PATH)
                baseline = _baseline(prim)
                editor.apply([await self._write_cutout(stage, out)])
                self.assertEqual(len(_remix_ref_children(prim, baseline)), 1)

                # Act
                omni.kit.undo.undo()

                # Assert
                self.assertEqual(len(_capture_references(prim)), 1)
                self.assertEqual(_remix_ref_children(prim, baseline), [])

    async def _add_replacement(self, stage: Usd.Stage, project_url: OmniUrl, layer: Sdf.Layer) -> tuple[str, str]:
        """Reference a textured replacement file from the fixture mesh and return the file and the card path."""
        project_dir = Path(OmniUrl(project_url.parent_url).path)
        texture = write_alpha_texture(project_dir / "card.png", np.full((8, 8), 255, dtype=np.uint8))
        original = write_replacement_file(project_dir / "fern01.usda", texture)
        core = AssetReplacementsCore("")
        self.addCleanup(core.destroy)
        _, ref_path = core.add_new_reference(
            stage, Sdf.Path(_MESH_PATH), original, AssetReplacementsCore.get_ref_default_prim_tag(), layer
        )
        return original, f"{ref_path}/XForms/card/mesh"

    def _reference_of(self, stage: Usd.Stage, prim_path: str) -> str:
        prim = stage.GetPrimAtPath(prim_path)
        references = [reference for reference, _ in omni.usd.get_composed_references_from_prim(prim, False)]
        self.assertEqual(len(references), 1)
        return references[0].assetPath

    async def test_apply_with_replacement_swaps_reference_in_place_and_keeps_overrides(self):
        async with open_test_project(_PROJECT, _RESOURCES_EXT) as project_url:
            # Arrange
            stage = omni.usd.get_context().get_stage()
            layer = self._set_replacement_edit_target(project_url, stage)
            original, card_path = await self._add_replacement(stage, project_url, layer)
            original_text = Path(original).read_text()
            stage.GetPrimAtPath(card_path).GetAttribute("doubleSided").Set(False)
            target = resolve_conversion_target(stage, card_path)
            source = read_mesh_sources(stage, list(target.meshes), target)[0]
            self.assertIsNone(source.skip_reason)
            cut_mesh = _pass_through_cut_mesh(source)
            output = write_cutout_replacement(
                target.original_file, target.output_file, [(source.file_prim_path, cut_mesh)], True
            )
            result = MeshCutoutResult(source, cut_mesh, 2, 2, 0.0, output_path=output)
            editor = AlphaCutoutStageEditor("")
            self.addCleanup(editor.destroy)

            # Act
            outcomes = editor.apply([result])

            # Assert
            self.assertEqual(len(outcomes), 1)
            self.assertTrue(outcomes[0].reference_added)
            self.assertEqual(outcomes[0].reference_prim_path, target.root_path)
            self.assertTrue(self._reference_of(stage, target.root_path).endswith(f"fern01{REPLACEMENT_SUFFIX}.usda"))
            self.assertFalse(stage.GetPrimAtPath(card_path).GetAttribute("doubleSided").Get())
            self.assertEqual(len(UsdGeom.Mesh(stage.GetPrimAtPath(card_path)).GetFaceVertexCountsAttr().Get()), 2)
            self.assertEqual(Path(original).read_text(), original_text)

            # Undo restores the original reference and redo swaps it back.
            omni.kit.undo.undo()
            self.assertTrue(self._reference_of(stage, target.root_path).endswith("fern01.usda"))
            omni.kit.undo.redo()
            self.assertTrue(self._reference_of(stage, target.root_path).endswith(f"fern01{REPLACEMENT_SUFFIX}.usda"))

            # A second apply finds the reference in place and changes nothing.
            self.assertFalse(editor.apply([result])[0].reference_added)

    async def test_get_edit_layer_problem_with_capture_edit_target_reports_replacement_layer_required(self):
        async with open_test_project(_PROJECT, _RESOURCES_EXT) as project_url:
            # Arrange
            stage = omni.usd.get_context().get_stage()
            capture_layer = Sdf.Layer.FindOrOpen(str(OmniUrl(project_url.parent_url) / "deps/captures/capture.usda"))
            stage.SetEditTarget(Usd.EditTarget(capture_layer))
            editor = AlphaCutoutStageEditor("")
            self.addCleanup(editor.destroy)

            # Act
            problem = editor.get_edit_layer_problem()

            # Assert
            self.assertIn("replacement layer", problem)

    async def test_get_edit_layer_problem_with_replacement_edit_target_returns_none(self):
        async with open_test_project(_PROJECT, _RESOURCES_EXT) as project_url:
            # Arrange
            stage = omni.usd.get_context().get_stage()
            self._set_replacement_edit_target(project_url, stage)
            editor = AlphaCutoutStageEditor("")
            self.addCleanup(editor.destroy)

            # Act
            problem = editor.get_edit_layer_problem()

            # Assert
            self.assertIsNone(problem)
