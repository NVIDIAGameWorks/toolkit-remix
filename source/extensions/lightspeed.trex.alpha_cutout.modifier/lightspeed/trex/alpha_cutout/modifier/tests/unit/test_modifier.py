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

__all__ = ["TestAlphaCardToMesh"]

import dataclasses
import json
import tempfile
from pathlib import Path

import numpy as np
import omni.client
from lightspeed.common import constants
from lightspeed.trex.alpha_cutout.core import (
    CutoutParameters,
    MeshConversion,
    parameters_from_values,
    read_mesh_source,
    snapshot_material,
    write_cutout_file,
)
from lightspeed.trex.alpha_cutout.core.tests.unit.fixtures import (
    MATERIAL_PATH,
    MESH_PRIM_PATH,
    MESH_ROOT_PATH,
    REPLACEMENT_CARD_FILE_PATH,
    build_capture_stage,
    quad_cut_mesh,
    write_alpha_texture,
    write_replacement_file,
)
from lightspeed.trex.alpha_cutout.modifier.job import AlphaCardToMeshJob, cutout_root_name, output_file_name
from lightspeed.trex.alpha_cutout.modifier.modifier import AlphaCardToMesh
from lightspeed.trex.alpha_cutout.modifier.report import ConversionReport, MeshReport
from lightspeed.trex.alpha_cutout.modifier.values import (
    MATERIAL_KEY,
    MATERIAL_PRIM_KEY,
    MESHES_KEY,
    PRIM_PATH_KEY,
    TEXTURE_KEY,
)
from lightspeed.trex.asset_pipeline.core.jobs import MeshOptimizationJob
from lightspeed.trex.asset_pipeline.core.jobs.asset_replace_apply_handler import AssetReplaceApplyHandler
from lightspeed.trex.asset_pipeline.core.jobs.asset_replace_apply_target import AssetReplaceApplyTarget
from lightspeed.trex.asset_pipeline.core.jobs.models import ReferenceTarget
from omni.flux.job_queue.core.job import JobGraph, JobOutputs
from omni.flux.job_queue.core.serializer import deserialize, serialize
from omni.kit.test import AsyncTestCase
from pxr import Sdf, Usd, UsdGeom, UsdShade

_REF_PATH = f"{MESH_ROOT_PATH}/ref_abc"
_CARD_STAGE_PATH = f"{_REF_PATH}/XForms/card/mesh"
_CAPTURE_MESH_FILE_PATH = "/mesh_AAAAAAAAAAAAAAAA/mesh"


def _visible_inputs(values: dict) -> set[str]:
    return {item.name for item in AlphaCardToMesh.inputs if item.visible_if is None or item.visible_if(values)}


def _target(owner_path: str, file: str, layer: Sdf.Layer) -> AssetReplaceApplyTarget:
    reference = Sdf.Reference(file)
    return AssetReplaceApplyTarget(
        context_name="",
        project_path=layer.identifier,
        edit_target_layer=layer.identifier,
        reference_targets=(ReferenceTarget(owner_path, reference, layer.identifier),),
    )


class TestAlphaCardToMesh(AsyncTestCase):
    """Test the modifier declaration and the graph it builds."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._root = Path(self._temp_dir.name)
        self._texture = write_alpha_texture(self._root / "alpha.png", np.full((4, 4), 255, np.uint8))
        self._modifier = AlphaCardToMesh()

    def tearDown(self):
        self._temp_dir.cleanup()

    def _build(
        self, stage, source_url: str, prim_paths: tuple[str, ...], target
    ) -> tuple[JobGraph, AlphaCardToMeshJob]:
        job = AlphaCardToMeshJob(name="cutout", context_name="", source_url=source_url, prim_paths=prim_paths)
        graph = JobGraph(name="cutout")
        graph.add_job(job)
        self._modifier.build_graph(stage, graph, job, target)
        return graph, job

    async def test_inputs_mirror_the_cutout_parameters_and_their_defaults(self):
        # Arrange
        defaults = CutoutParameters()

        # Act
        values = {item.name: item.default for item in AlphaCardToMesh.inputs}

        # Assert
        self.assertEqual(set(values), {field.name for field in dataclasses.fields(CutoutParameters)})
        self.assertEqual(parameters_from_values(values), defaults)
        self.assertEqual({type(item.default) for item in AlphaCardToMesh.inputs}, {int, float, bool})

    async def test_output_file_name_keeps_the_capture_hash_and_prefixes_other_models(self):
        # Act / Assert
        self.assertEqual(output_file_name("C:/caps/meshes/mesh_ED00DD5BABD25B03.usd"), "cutout_ED00DD5BABD25B03.usda")
        self.assertEqual(output_file_name("C:/mod/assets/fern01.usda"), "cutout_fern01.usda")

    async def test_dependent_inputs_show_only_while_their_option_is_enabled(self):
        # Arrange
        defaults = {item.name: item.default for item in AlphaCardToMesh.inputs}
        thicken_inputs = {"thickness", "thicken_back_face", "thicken_anti_stretch", "smooth_normals", "smoothing"}
        everything_on = defaults | {"thicken": True, "smooth_normals": True, "up_normals": True}
        thicken_only = defaults | {"thicken": True, "smooth_normals": False, "up_normals": False}
        everything_off = defaults | {"thicken": False, "smooth_normals": True, "up_normals": False}

        # Act
        visible_on = _visible_inputs(everything_on)
        visible_thicken = _visible_inputs(thicken_only)
        visible_off = _visible_inputs(everything_off)

        # Assert
        self.assertEqual(visible_on, set(defaults))
        self.assertEqual(visible_thicken, set(defaults) - {"smoothing", "up_amount"})
        self.assertEqual(visible_off, set(defaults) - thicken_inputs - {"up_amount"})

    async def test_summarize_result_counts_the_converted_meshes_and_lists_a_few(self):
        # Arrange
        cards = [MeshReport(f"/Root/XForms/card{index}/mesh", 4, 2, 40, 20) for index in range(5)]
        trunk = MeshReport("/Root/XForms/trunk/mesh", 8, 12, 0, 0, "The texture is opaque.")
        outputs = JobOutputs({AlphaCardToMeshJob.REPORT: ConversionReport((*cards[:3], trunk, *cards[3:]))})

        # Act
        summary = self._modifier.summarize_result(outputs)

        # Assert
        self.assertEqual(
            summary.splitlines(),
            [
                "Alpha Card to Mesh: Converted 5 of 6 meshes",
                "XForms/card0/mesh: 2 -> 20 faces, 4 -> 40 vertices",
                "XForms/card1/mesh: 2 -> 20 faces, 4 -> 40 vertices",
                "XForms/card2/mesh: 2 -> 20 faces, 4 -> 40 vertices",
                "XForms/trunk/mesh: Skipped: The texture is opaque.",
                "and 2 more meshes",
            ],
        )

    async def test_cutout_root_name_renames_capture_mesh_roots_only(self):
        # Arrange
        capture = Usd.Stage.CreateInMemory()
        capture.SetDefaultPrim(UsdGeom.Xform.Define(capture, "/mesh_AAAAAAAAAAAAAAAA").GetPrim())
        replacement = Usd.Stage.Open(write_replacement_file(self._root / "fern01.usda", self._texture))

        # Act
        capture_name = cutout_root_name(capture, "cutout_AAAAAAAAAAAAAAAA")
        replacement_name = cutout_root_name(replacement, "cutout_fern01")

        # Assert
        self.assertEqual(capture_name, "cutout_AAAAAAAAAAAAAAAA")
        self.assertIsNone(replacement_name)

    async def test_is_compatible_accepts_meshes_asset_rows_and_reference_prims(self):
        # Arrange
        stage = build_capture_stage(self._texture)
        ref_prim = UsdGeom.Xform.Define(stage, _REF_PATH).GetPrim()
        ref_prim.CreateAttribute(constants.IS_REMIX_REF_ATTR, Sdf.ValueTypeNames.Bool).Set(True)
        plain_xform = UsdGeom.Xform.Define(stage, f"{_REF_PATH}/XForms").GetPrim()
        UsdGeom.Mesh.Define(stage, f"{_REF_PATH}/XForms/mesh")
        empty_asset = UsdGeom.Xform.Define(stage, "/RootNode/meshes/mesh_BBBBBBBBBBBBBBBB").GetPrim()

        # Act
        accepted = [
            self._modifier.is_compatible(prim)
            for prim in (stage.GetPrimAtPath(MESH_PRIM_PATH), stage.GetPrimAtPath(MESH_ROOT_PATH), ref_prim)
        ]
        rejected = [self._modifier.is_compatible(prim) for prim in (plain_xform, empty_asset)]

        # Assert
        self.assertEqual(accepted, [True, True, True])
        self.assertEqual(rejected, [False, False])

    async def test_build_graph_with_reference_prim_lists_every_textured_mesh_below_it_once(self):
        # Arrange
        source = write_replacement_file(self._root / "fern01.usda", self._texture)
        stage = build_capture_stage(self._texture)
        ref_prim = UsdGeom.Xform.Define(stage, _REF_PATH).GetPrim()
        ref_prim.CreateAttribute(constants.IS_REMIX_REF_ATTR, Sdf.ValueTypeNames.Bool).Set(True)
        ref_prim.GetReferences().AddReference(source)
        target = _target(_REF_PATH, source, stage.GetRootLayer())

        # Act
        _, job = self._build(stage, source, (_REF_PATH, _CARD_STAGE_PATH), target)

        # Assert
        self.assertIsNone(job.skip_reason)
        self.assertEqual([entry[PRIM_PATH_KEY] for entry in job.values[MESHES_KEY]], [REPLACEMENT_CARD_FILE_PATH])

    async def test_mesh_report_counts_both_meshes_and_round_trips_through_the_queue_codecs(self):
        # Arrange
        stage = build_capture_stage(self._texture)
        source = read_mesh_source(stage, MESH_PRIM_PATH, self._texture)
        report = ConversionReport(
            (
                MeshReport.from_conversion(MESH_PRIM_PATH, source, quad_cut_mesh()),
                MeshReport.from_conversion(MESH_PRIM_PATH, source, None, "opaque"),
            )
        )

        # Act
        restored = deserialize(serialize(report))

        # Assert
        self.assertEqual(restored, report)
        self.assertEqual((report.meshes[0].source_vertices, report.meshes[0].source_faces), (4, 2))
        self.assertEqual((report.meshes[0].vertices, report.meshes[0].faces), (4, 2))
        self.assertEqual(
            (report.meshes[1].vertices, report.meshes[1].faces, report.meshes[1].skip_reason), (0, 0, "opaque")
        )

    async def test_build_graph_without_prims_lists_every_textured_mesh_of_the_file(self):
        # Arrange
        source = write_replacement_file(self._root / "fern01.usda", self._texture)

        # Act
        graph, job = self._build(None, source, (), None)

        # Assert
        self.assertIsNone(job.skip_reason)
        self.assertEqual(
            job.values[MESHES_KEY],
            [
                {
                    PRIM_PATH_KEY: REPLACEMENT_CARD_FILE_PATH,
                    TEXTURE_KEY: job.values[MESHES_KEY][0][TEXTURE_KEY],
                    MATERIAL_KEY: None,
                }
            ],
        )
        self.assertTrue(job.values[MESHES_KEY][0][TEXTURE_KEY].lower().endswith("/alpha.png"))
        self.assertEqual(len(graph.jobs), 4)
        (mesh_job,) = [item for item in graph.jobs if isinstance(item, MeshOptimizationJob)]
        self.assertIsNone(mesh_job.apply_binding.target)

    async def test_build_graph_with_replacement_prim_maps_it_into_the_file_without_a_snapshot(self):
        # Arrange
        source = write_replacement_file(self._root / "fern01.usda", self._texture)
        stage = Usd.Stage.CreateInMemory()
        UsdGeom.Xform.Define(stage, MESH_ROOT_PATH)
        ref_prim = UsdGeom.Xform.Define(stage, _REF_PATH).GetPrim()
        ref_prim.CreateAttribute(constants.IS_REMIX_REF_ATTR, Sdf.ValueTypeNames.Bool).Set(True)
        ref_prim.GetReferences().AddReference(source)
        target = _target(_REF_PATH, source, stage.GetRootLayer())

        # Act
        graph, job = self._build(stage, source, (_CARD_STAGE_PATH,), target)

        # Assert
        self.assertIsNone(job.skip_reason)
        (entry,) = job.values[MESHES_KEY]
        self.assertEqual(entry[PRIM_PATH_KEY], REPLACEMENT_CARD_FILE_PATH)
        self.assertIsNone(entry[MATERIAL_KEY])
        (mesh_job,) = [item for item in graph.jobs if isinstance(item, MeshOptimizationJob)]
        self.assertIs(mesh_job.apply_binding.handler_type, AssetReplaceApplyHandler)
        self.assertEqual(mesh_job.apply_binding.target, target)

    async def test_build_graph_with_capture_prim_snapshots_the_composed_material(self):
        # Arrange: the capture mesh file holds the geometry only; the material is bound in the project stage.
        stage = build_capture_stage(self._texture)
        file_stage = Usd.Stage.CreateNew(str(self._root / "mesh.usda"))
        file_stage.SetDefaultPrim(UsdGeom.Xform.Define(file_stage, "/mesh_AAAAAAAAAAAAAAAA").GetPrim())
        Sdf.CopySpec(
            stage.GetRootLayer(), Sdf.Path(MESH_PRIM_PATH), file_stage.GetRootLayer(), Sdf.Path(_CAPTURE_MESH_FILE_PATH)
        )
        file_stage.GetRootLayer().Save()
        source = str(self._root / "mesh.usda")
        stage.RemovePrim(MESH_PRIM_PATH)
        stage.GetPrimAtPath(MESH_ROOT_PATH).GetReferences().AddReference(source)
        target = _target(MESH_ROOT_PATH, source, stage.GetRootLayer())

        # Act
        _, job = self._build(stage, source, (MESH_PRIM_PATH,), target)

        # Assert
        (entry,) = job.values[MESHES_KEY]
        self.assertEqual(entry[PRIM_PATH_KEY], _CAPTURE_MESH_FILE_PATH)
        self.assertIsNotNone(entry[MATERIAL_KEY])
        json.dumps(job.values)
        names = {attribute["name"] for attribute in entry[MATERIAL_KEY]["attributes"]}
        self.assertIn("inputs:diffuse_texture", names)
        self.assertEqual(UsdShade.Material(stage.GetPrimAtPath(MATERIAL_PATH)).GetPrim().IsValid(), True)

    async def test_build_graph_on_a_cutout_reads_the_original_model_again(self):
        # Arrange: the project references a published cutout of the capture mesh; the capture file still exists.
        stage = build_capture_stage(self._texture)
        capture = Usd.Stage.CreateNew(str(self._root / "mesh.usda"))
        capture.SetDefaultPrim(UsdGeom.Xform.Define(capture, "/mesh_AAAAAAAAAAAAAAAA").GetPrim())
        Sdf.CopySpec(
            stage.GetRootLayer(), Sdf.Path(MESH_PRIM_PATH), capture.GetRootLayer(), Sdf.Path(_CAPTURE_MESH_FILE_PATH)
        )
        capture.GetRootLayer().Save()
        capture_file = str(self._root / "mesh.usda")
        snapshot = snapshot_material(UsdShade.Material(stage.GetPrimAtPath(MATERIAL_PATH)))
        cutout_file = str(
            write_cutout_file(
                capture_file,
                self._root / "cutout.usda",
                [MeshConversion(_CAPTURE_MESH_FILE_PATH, quad_cut_mesh(), snapshot, MATERIAL_PATH)],
                True,
            )
        )
        stage.RemovePrim(MESH_PRIM_PATH)
        ref_prim = UsdGeom.Xform.Define(stage, _REF_PATH).GetPrim()
        ref_prim.CreateAttribute(constants.IS_REMIX_REF_ATTR, Sdf.ValueTypeNames.Bool).Set(True)
        ref_prim.GetReferences().AddReference(cutout_file)
        target = _target(_REF_PATH, cutout_file, stage.GetRootLayer())

        # Act
        _, job = self._build(stage, cutout_file, (f"{_REF_PATH}/mesh",), target)

        # Assert
        self.assertIsNone(job.skip_reason)
        self.assertEqual(job.source_url, omni.client.normalize_url(capture_file))
        (entry,) = job.values[MESHES_KEY]
        self.assertEqual(entry[PRIM_PATH_KEY], _CAPTURE_MESH_FILE_PATH)
        self.assertEqual(entry[MATERIAL_PRIM_KEY], MATERIAL_PATH)
        self.assertIsNotNone(entry[MATERIAL_KEY])

    async def test_build_graph_on_a_cutout_file_reads_the_original_model_again(self):
        # Arrange: a cutout of a capture mesh is given as a model file, without a project.
        stage = build_capture_stage(self._texture)
        capture = Usd.Stage.CreateNew(str(self._root / "mesh.usda"))
        capture.SetDefaultPrim(UsdGeom.Xform.Define(capture, "/mesh_AAAAAAAAAAAAAAAA").GetPrim())
        Sdf.CopySpec(
            stage.GetRootLayer(), Sdf.Path(MESH_PRIM_PATH), capture.GetRootLayer(), Sdf.Path(_CAPTURE_MESH_FILE_PATH)
        )
        capture.GetRootLayer().Save()
        capture_file = str(self._root / "mesh.usda")
        snapshot = snapshot_material(UsdShade.Material(stage.GetPrimAtPath(MATERIAL_PATH)))
        (self._root / "out").mkdir()
        cutout_file = str(
            write_cutout_file(
                capture_file,
                self._root / "out" / "cutout.usda",
                [MeshConversion(_CAPTURE_MESH_FILE_PATH, quad_cut_mesh(), snapshot, MATERIAL_PATH)],
                True,
            )
        )

        # Act
        _, job = self._build(None, cutout_file, (), None)

        # Assert
        self.assertIsNone(job.skip_reason)
        self.assertEqual(job.source_url, omni.client.normalize_url(capture_file))
        (entry,) = job.values[MESHES_KEY]
        self.assertEqual(entry[PRIM_PATH_KEY], _CAPTURE_MESH_FILE_PATH)
        self.assertEqual(entry[MATERIAL_PRIM_KEY], MATERIAL_PATH)
        names = {attribute["name"] for attribute in entry[MATERIAL_KEY]["attributes"]}
        self.assertIn("inputs:diffuse_texture", names)

    async def test_build_graph_without_textured_mesh_sets_skip_reason(self):
        # Arrange
        source = write_replacement_file(self._root / "fern01.usda", None)

        # Act
        graph, job = self._build(None, source, (), None)

        # Assert
        self.assertIn("diffuse texture", job.skip_reason)
        self.assertEqual(len(graph.jobs), 1)
