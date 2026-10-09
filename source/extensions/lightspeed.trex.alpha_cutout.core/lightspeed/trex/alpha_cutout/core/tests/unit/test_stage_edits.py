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

__all__ = ["TestAlphaCutoutStageEditor"]

import tempfile
from pathlib import Path
from unittest.mock import Mock

import omni.client
import omni.usd
from lightspeed.common import constants
from lightspeed.trex.alpha_cutout.core.stage_edits import AlphaCutoutStageEditor
from lightspeed.trex.alpha_cutout.core.usd_reader import replacement_output_path
from omni.kit.test import AsyncTestCase
from pxr import Sdf, Usd, UsdGeom

from .fixtures import REPLACEMENT_REF_PATH, build_replacement_stage, write_replacement_file


def _write_tiny_layer(path: Path) -> str:
    layer = Sdf.Layer.CreateNew(str(path))
    stage = Usd.Stage.Open(layer)
    root = UsdGeom.Xform.Define(stage, "/cutout_AAAAAAAAAAAAAAAA")
    stage.SetDefaultPrim(root.GetPrim())
    layer.Save()
    return omni.client.normalize_url(str(path))


class TestAlphaCutoutStageEditor(AsyncTestCase):
    """Test the reference lookup and the edit target checks."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._temp_dir.cleanup()

    async def test_find_existing_cutout_reference_with_matching_child_reference_returns_it(self):
        # Arrange
        cutout = _write_tiny_layer(Path(self._temp_dir.name) / "cutout_AAAAAAAAAAAAAAAA.usda")
        stage = Usd.Stage.CreateInMemory()
        prim = UsdGeom.Xform.Define(stage, "/RootNode/meshes/mesh_AAAAAAAAAAAAAAAA").GetPrim()
        child = UsdGeom.Xform.Define(stage, "/RootNode/meshes/mesh_AAAAAAAAAAAAAAAA/ref_abc").GetPrim()
        child.CreateAttribute(constants.IS_REMIX_REF_ATTR, Sdf.ValueTypeNames.Bool).Set(True)
        child.GetReferences().AddReference(cutout)

        # Act
        found = AlphaCutoutStageEditor.find_existing_cutout_reference(prim, cutout.upper())

        # Assert
        self.assertIsNotNone(found)
        self.assertEqual(found[0].GetPath(), child.GetPath())

    async def test_find_existing_cutout_reference_with_other_reference_returns_none(self):
        # Arrange
        cutout = _write_tiny_layer(Path(self._temp_dir.name) / "cutout_AAAAAAAAAAAAAAAA.usda")
        other = _write_tiny_layer(Path(self._temp_dir.name) / "other.usda")
        stage = Usd.Stage.CreateInMemory()
        prim = UsdGeom.Xform.Define(stage, "/RootNode/meshes/mesh_AAAAAAAAAAAAAAAA").GetPrim()
        prim.GetReferences().AddReference(other)

        # Act
        found = AlphaCutoutStageEditor.find_existing_cutout_reference(prim, cutout)

        # Assert
        self.assertIsNone(found)

    async def test_swap_replacement_reference_replaces_reference_on_the_remix_ref_prim(self):
        # Arrange
        original = write_replacement_file(Path(self._temp_dir.name) / "fern01.usda", None)
        stage = build_replacement_stage(original)
        editor = AlphaCutoutStageEditor("")
        self.addCleanup(editor.destroy)
        editor._core = Mock()
        output = replacement_output_path(original)

        # Act
        changed, reason = editor._swap_replacement_reference(stage, stage.GetRootLayer(), REPLACEMENT_REF_PATH, output)

        # Assert
        self.assertTrue(changed)
        self.assertIsNone(reason)
        editor._core.replace_reference.assert_called_once()
        args, kwargs = editor._core.replace_reference.call_args
        self.assertEqual(args[1], Sdf.Path(REPLACEMENT_REF_PATH))
        self.assertEqual(args[4], output)
        self.assertFalse(kwargs["remove_if_remix_ref"])
        self.assertFalse(kwargs["create_if_remix_ref"])
        self.assertFalse(kwargs["use_undo_group"])

    async def test_swap_replacement_reference_already_pointing_at_output_changes_nothing(self):
        # Arrange
        output = write_replacement_file(Path(self._temp_dir.name) / "fern01_cutout_replacement.usda", None)
        stage = build_replacement_stage(output)
        editor = AlphaCutoutStageEditor("")
        self.addCleanup(editor.destroy)
        editor._core = Mock()

        # Act
        changed, reason = editor._swap_replacement_reference(stage, stage.GetRootLayer(), REPLACEMENT_REF_PATH, output)

        # Assert
        self.assertFalse(changed)
        self.assertIsNone(reason)
        editor._core.replace_reference.assert_not_called()

    async def test_get_edit_layer_problem_without_stage_reports_no_project(self):
        # Arrange
        context = omni.usd.get_context()
        if context.get_stage():
            await context.close_stage_async()
        editor = AlphaCutoutStageEditor("")

        try:
            # Act
            problem = editor.get_edit_layer_problem()
        finally:
            editor.destroy()

        # Assert
        self.assertEqual(problem, "No project is open.")

    async def test_get_edit_layer_problem_with_anonymous_edit_target_reports_replacement_layer_required(self):
        # Arrange
        context = omni.usd.get_context()
        await context.new_stage_async()
        editor = AlphaCutoutStageEditor("")

        try:
            # Act
            problem = editor.get_edit_layer_problem()
        finally:
            editor.destroy()
            await context.close_stage_async()

        # Assert
        self.assertIn("replacement layer", problem)
