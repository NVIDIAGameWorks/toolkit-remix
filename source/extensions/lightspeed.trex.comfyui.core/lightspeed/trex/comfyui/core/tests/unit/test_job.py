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

import dataclasses
import json
import pathlib
import shutil
import tempfile
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

from lightspeed.trex.asset_pipeline.core.jobs.models import (
    MeshOptimizationRequest,
    MeshOptimizationResult,
    ProcessedTexture,
    TextureOptimizationItem,
    TextureOptimizationResult,
)
from lightspeed.trex.asset_pipeline.core.metadata import MetadataApplyReceipt
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core.errors import ApplyExecutionError, JobExecutionError
from omni.flux.job_queue.core.job import JobInputs, JobProgress
from omni.flux.job_queue.core.serializer import deserialize, serialize
from omni.kit.test import AsyncTestCase
from pxr import Sdf, Usd, UsdGeom

from ... import apply_handler as apply_handler_module
from ... import job as job_module
from ...api import ComfyUIExecutionError
from ...apply_handler import ComfyUIAssetApplyHandler, ComfyUITextureApplyHandler
from ...connection import set_connected_endpoint
from ...enums import MeshReferenceSelection, OutputApplyBehavior, RemixType
from ...job import ComfyUIAssetJob, ComfyUIJob, ViewerRenderedInputError
from ...models import (
    ComfyUIApplyReceipt,
    ComfyUIApplyTarget,
    ComfyUIAssetApplyTarget,
    ComfyUIFileResult,
    ComfyUIInputBinding,
    ComfyUIWorkflowRequest,
    ReferenceTarget,
    Workflow,
    WorkflowOutput,
)


def _make_workflow_request(
    *,
    prompt: dict[str, Any] | None = None,
    input_bindings: tuple[ComfyUIInputBinding, ...] = (),
    output_specs: tuple[WorkflowOutput, ...] = (),
    output_url: str | None = "C:/project/assets/ingested/comfyui/test",
) -> ComfyUIWorkflowRequest:
    """Create a complete workflow request for job tests."""
    return ComfyUIWorkflowRequest(
        prompt={} if prompt is None else prompt,
        input_bindings=input_bindings,
        client_id="test-client",
        timeout=300.0,
        output_url=output_url,
        workflow=Workflow(output_specs=list(output_specs)),
    )


def _make_processed_textures(*keys: str, validation_passed: bool = True) -> TextureOptimizationResult:
    """Create processed texture results with canonical output semantics."""
    texture_types = {
        "albedo": TextureTypes.DIFFUSE,
        "normal_ogl": TextureTypes.NORMAL_OTH,
        "roughness": TextureTypes.ROUGHNESS,
        "internal": TextureTypes.OTHER,
    }
    return TextureOptimizationResult(
        items=tuple(
            ProcessedTexture(
                key=key,
                source_path=pathlib.Path(f"C:/queue/{key}.png"),
                asset_url=f"C:/published/{key}.dds",
                texture_type=texture_types[key],
            )
            for key in keys
        ),
        validation_passed=validation_passed,
    )


def _make_node_keyed_textures() -> TextureOptimizationResult:
    """Create albedo, normal, and roughness results keyed by node id, the way current jobs publish them.

    The fixture publishes "normal_ogl" as the converted NORMAL_OTH, the way the pipeline does.
    """
    processed = _make_processed_textures("albedo", "normal_ogl", "roughness")
    return dataclasses.replace(
        processed,
        items=tuple(dataclasses.replace(item, key=str(index)) for index, item in enumerate(processed.items, 10)),
    )


def _make_mesh_result(*, validation_passed: bool = True) -> MeshOptimizationResult:
    """Create an optimized mesh with one internal processed texture."""
    return MeshOptimizationResult(
        asset_url="C:/published/generated.glb",
        texture_result=_make_processed_textures("internal"),
        source_path=pathlib.Path("C:/queue/generated.glb"),
        validation_passed=validation_passed,
    )


def _make_texture_target(texture_targets: tuple[tuple[str, str], ...]) -> ComfyUIApplyTarget:
    """Create one exact texture Apply target."""
    return ComfyUIApplyTarget(
        context_name="texturecraft",
        project_path="C:/project/project.usda",
        edit_target_layer="C:/project/mod.usda",
        material_path="/World/Looks/Material",
        texture_targets=texture_targets,
    )


def _make_texture_receipt(
    *,
    original: tuple[tuple[str, str | None], ...] = (),
    applied: tuple[tuple[str, str | None], ...] = (),
) -> ComfyUIApplyReceipt:
    """Create one exact texture and metadata receipt."""
    return ComfyUIApplyReceipt(
        original_authored_values=original,
        original_compare_values=original,
        applied_compare_values=applied,
        metadata_receipt=MetadataApplyReceipt(prior_meta=()),
    )


def _make_asset_target(
    *,
    reference_targets: tuple[ReferenceTarget, ...] = (),
    texture_targets: tuple[tuple[str, str], ...] = (),
    behavior: Any = OutputApplyBehavior.APPEND,
) -> ComfyUIAssetApplyTarget:
    """Create one exact asset Apply target."""
    return ComfyUIAssetApplyTarget(
        context_name="texturecraft",
        project_path="C:/project/project.usda",
        edit_target_layer="C:/project/mod.usda",
        reference_targets=reference_targets,
        texture_targets=texture_targets,
        mesh_apply_behavior=behavior,
    )


class TestComfyUIJob(AsyncTestCase):
    """Test ComfyUI jobs, adapters, persistence, and Apply handlers."""

    async def setUp(self) -> None:
        """Clear the endpoint and isolate metadata reads from the filesystem."""
        set_connected_endpoint("texturecraft", None)
        metadata_capture = patch.object(
            apply_handler_module, "capture_metadata_receipt", return_value=MetadataApplyReceipt(prior_meta=())
        )
        metadata_capture.start()
        self.addCleanup(metadata_capture.stop)

    async def tearDown(self) -> None:
        """Clear the connected endpoint after each test."""
        set_connected_endpoint("texturecraft", None)

    async def test_asset_apply_rejects_external_texture_edit_with_equal_snapshots(self):
        """Equal saved textures do not permit an external texture edit."""
        path = "/World/Looks/Material/Shader.inputs:diffuse_texture"
        value = _make_mesh_result()
        shared = ((path, value.texture_result.items[0].asset_url),)
        target = _make_asset_target(texture_targets=(("internal", path),))
        receipt = _make_texture_receipt(original=shared, applied=shared)
        layer = MagicMock(anonymous=True)
        layer.GetAttributeAtPath.return_value.default = Sdf.AssetPath("C:/external/changed.dds")
        with (
            patch.object(apply_handler_module, "_get_apply_stage", return_value=(MagicMock(), layer)),
            patch.object(apply_handler_module, "_reference_state", return_value=("original", {})),
            patch.object(apply_handler_module, "_write_output_metadata", AsyncMock()) as write_metadata,
            patch.object(apply_handler_module, "revert_metadata") as revert_metadata,
            patch.object(apply_handler_module, "Setup") as setup,
            self.assertRaises(ApplyExecutionError) as error_context,
        ):
            await ComfyUIAssetApplyHandler().apply(value, target, receipt)
        self.assertIn("changed outside", error_context.exception.reason)
        write_metadata.assert_not_called()
        revert_metadata.assert_not_called()
        setup.assert_not_called()

    async def test_asset_revert_rejects_external_texture_edit_with_equal_snapshots(self):
        """Equal saved textures do not permit an external texture edit."""
        path = "/World/Looks/Material/Shader.inputs:diffuse_texture"
        value = _make_mesh_result()
        shared = ((path, value.texture_result.items[0].asset_url),)
        target = _make_asset_target(texture_targets=(("internal", path),))
        receipt = _make_texture_receipt(original=shared, applied=shared)
        layer = MagicMock(anonymous=True)
        layer.GetAttributeAtPath.return_value.default = Sdf.AssetPath("C:/external/changed.dds")
        with (
            patch.object(apply_handler_module, "_get_apply_stage", return_value=(MagicMock(), layer)),
            patch.object(apply_handler_module, "_reference_state", return_value=("applied", {})),
            patch.object(apply_handler_module, "_write_output_metadata", AsyncMock()) as write_metadata,
            patch.object(apply_handler_module, "revert_metadata") as revert_metadata,
            patch.object(apply_handler_module, "Setup") as setup,
            self.assertRaises(ApplyExecutionError) as error_context,
        ):
            await ComfyUIAssetApplyHandler().revert(value, target, receipt)
        self.assertIn("changed outside", error_context.exception.reason)
        write_metadata.assert_not_called()
        revert_metadata.assert_not_called()
        setup.assert_not_called()

    async def test_schedule_block_reason_requires_the_saved_endpoint(self):
        """A saved job waits until its exact server is connected."""
        # Arrange
        job = ComfyUIJob(context_name="texturecraft", scheme="HTTP", host="Comfy-A", port=8188)
        set_connected_endpoint("texturecraft", ("http", "comfy-b", 8188))

        # Act
        reason = job.get_schedule_block_reason()

        # Assert
        self.assertEqual(
            reason,
            "This job is waiting for http://comfy-a:8188. The current connection is http://comfy-b:8188. "
            "Connect to the original server or use Change Server for this job.",
        )

    async def test_execute_returns_only_texture_optimization_request(self):
        """Execution returns every declared file through one exact output port."""
        # Arrange
        api = MagicMock()
        api.submit_prompt = AsyncMock(return_value="prompt-123")
        api.wait_for_prompt_completion = AsyncMock(
            return_value={
                "prompt-123": {
                    "outputs": {
                        "10": {"images": [{"filename": "albedo.png", "type": "output"}]},
                        "20": {"3d": [{"filename": "generated.glb", "type": "output"}]},
                    }
                }
            }
        )
        api.download_file = AsyncMock(side_effect=lambda _file, destination: destination)
        request = _make_workflow_request(
            output_specs=(
                WorkflowOutput(
                    node_id="20",
                    remix_type=RemixType.MESH_FILE_PATH,
                    order=2,
                    apply_behavior=OutputApplyBehavior.APPEND,
                ),
                WorkflowOutput(
                    node_id="10",
                    remix_type=RemixType.TEXTURE_FILE_PATH,
                    order=1,
                    texture_type="albedo",
                    apply_behavior=OutputApplyBehavior.REPLACE,
                ),
            )
        )
        job = ComfyUIJob()
        progress = AsyncMock()

        with patch.object(job_module, "ComfyUIAPI", return_value=api) as api_type:
            # Act
            outputs = await job.execute(
                pathlib.Path("C:/jobs"),
                JobInputs({ComfyUIJob.WORKFLOW_REQUEST: request}),
                progress,
            )

        # Assert
        self.assertEqual(tuple(outputs), (ComfyUIJob.GENERATED_TEXTURES,))
        request_output = outputs[ComfyUIJob.GENERATED_TEXTURES]
        self.assertEqual(
            request_output.items,
            (
                TextureOptimizationItem(
                    "10", pathlib.Path("C:/jobs/outputs/prompt-123/albedo.png"), TextureTypes.DIFFUSE
                ),
            ),
        )
        self.assertEqual(request_output.source_root, pathlib.Path("C:/jobs/outputs/prompt-123"))
        self.assertEqual(request_output.output_url, f"{request.output_url}/textures")
        api_type.assert_called_once_with("http", "127.0.0.1", 8188)
        progress.assert_awaited_with(JobProgress(completed=4, total=4, detail="Downloaded 2 generated files."))

    async def test_execute_wraps_submission_failure_and_stops_before_polling(self):
        """A failed prompt submission reports a safe reason, keeps the diagnostic, and never polls or downloads."""
        # Arrange
        api = MagicMock()
        api.submit_prompt = AsyncMock(side_effect=ConnectionError("socket reset by 10.0.0.7"))
        api.wait_for_prompt_completion = AsyncMock()
        api.download_file = AsyncMock()
        job = ComfyUIJob()

        with patch.object(job_module, "ComfyUIAPI", return_value=api):
            # Act
            with self.assertRaises(JobExecutionError) as error_context:
                await job.execute(
                    pathlib.Path("C:/jobs"),
                    JobInputs({ComfyUIJob.WORKFLOW_REQUEST: _make_workflow_request()}),
                    AsyncMock(),
                )

        # Assert
        self.assertEqual(
            error_context.exception.reason,
            "ComfyUI could not start this workflow. Check the server connection and workflow, then try again.",
        )
        self.assertIsInstance(error_context.exception.diagnostic, ConnectionError)
        api.wait_for_prompt_completion.assert_not_awaited()
        api.download_file.assert_not_awaited()

    async def test_upload_mesh_preserves_sublayers_references_and_textures(self):
        for mesh_first in (False, True):
            with self.subTest(mesh_first=mesh_first), tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory)
                source = root / "source"
                source.mkdir()
                (source / "textures").mkdir()
                texture = source / "textures" / "color.png"
                texture.write_bytes(b"texture-content")
                (source / "OmniPBR.mdl").write_text("mdl 1.0;", encoding="utf-8")
                geometry = Usd.Stage.CreateNew(str(source / "geometry.usda"))
                mesh = UsdGeom.Mesh.Define(geometry, "/Model")
                mesh.CreatePointsAttr([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
                mesh.GetPrim().CreateAttribute("texture", Sdf.ValueTypeNames.Asset).Set(
                    Sdf.AssetPath("textures/color.png")
                )
                mesh.GetPrim().CreateAttribute("module", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("OmniPBR.mdl"))
                mesh.GetPrim().CreateAttribute("searchModule", Sdf.ValueTypeNames.Asset).Set(
                    Sdf.AssetPath("SearchPath.mdl")
                )
                geometry.SetDefaultPrim(mesh.GetPrim())
                geometry.GetRootLayer().Save()
                child = Usd.Stage.CreateNew(str(source / "child.usda"))
                child.DefinePrim("/Model").GetReferences().AddReference(str(source / "geometry.usda"))
                child.GetRootLayer().Save()
                layer = Sdf.Layer.CreateNew(str(source / "model.usda"))
                layer.subLayerPaths = ["child.usda"]
                layer.Save()
                second_layer = Sdf.Layer.CreateNew(str(source / "other_model.usda"))
                second_layer.subLayerPaths = ["child.usda"]
                second_layer.Save()
                source_layers = (layer, second_layer, child.GetRootLayer(), geometry.GetRootLayer())
                source_contents = [item.ExportToString() for item in source_layers]
                binding = ComfyUIInputBinding("1.inputs.model", RemixType.MESH_FILE_PATH, layer.identifier)
                texture_binding = ComfyUIInputBinding(
                    "2.inputs.image",
                    RemixType.TEXTURE_FILE_PATH,
                    str(source / "textures" / ".." / "textures" / "color.png"),
                )
                second_binding = ComfyUIInputBinding(
                    "3.inputs.model", RemixType.MESH_FILE_PATH, second_layer.identifier
                )
                child_binding = ComfyUIInputBinding(
                    "4.inputs.model", RemixType.MESH_FILE_PATH, child.GetRootLayer().identifier
                )
                mesh_bindings = (binding, second_binding, child_binding)
                bindings = (*mesh_bindings, texture_binding) if mesh_first else (texture_binding, *mesh_bindings)
                request = _make_workflow_request(input_bindings=bindings)
                server = root / "server"

                async def upload(path, *, subfolder, convert_dds, server=server):
                    del convert_dds
                    name = pathlib.Path(path).name
                    if name == "color.png":
                        name, subfolder = "returned-texture.png", "returned/textures"
                    destination = server / subfolder / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, destination)
                    return {"name": name, "subfolder": subfolder, "type": "input"}

                api = MagicMock()
                api.upload_file = AsyncMock(side_effect=upload)
                uploaded = await ComfyUIJob()._upload_inputs(api, request)
                self.assertEqual([item.ExportToString() for item in source_layers], source_contents)
                self.assertEqual(
                    sorted(pathlib.Path(item.args[0]).name for item in api.upload_file.await_args_list),
                    ["child.usda", "color.png", "geometry.usda", "model.usda", "other_model.usda"],
                )
                shutil.rmtree(source)
                result = uploaded[(RemixType.MESH_FILE_PATH, binding.source)]
                self.assertEqual(result["name"], "model.usda")
                stage = Usd.Stage.Open(str(server / result["subfolder"] / result["name"]))
                uploaded_mesh = UsdGeom.Mesh(stage.GetPrimAtPath("/Model"))
                self.assertTrue(uploaded_mesh)
                self.assertEqual(list(uploaded_mesh.GetPointsAttr().Get()), [(0, 0, 0), (1, 0, 0), (0, 1, 0)])
                asset = uploaded_mesh.GetPrim().GetAttribute("texture").Get()
                self.assertEqual(pathlib.Path(asset.resolvedPath).read_bytes(), b"texture-content")
                texture_result = uploaded[(RemixType.TEXTURE_FILE_PATH, texture_binding.source)]
                self.assertEqual(
                    pathlib.Path(asset.resolvedPath), server / texture_result["subfolder"] / texture_result["name"]
                )
                self.assertEqual(uploaded_mesh.GetPrim().GetAttribute("module").Get().path, "OmniPBR.mdl")
                self.assertEqual(uploaded_mesh.GetPrim().GetAttribute("searchModule").Get().path, "SearchPath.mdl")
                for shared_binding, expected_name in (
                    (second_binding, "other_model.usda"),
                    (child_binding, "child.usda"),
                ):
                    shared_result = uploaded[(RemixType.MESH_FILE_PATH, shared_binding.source)]
                    self.assertEqual(shared_result["name"], expected_name)
                    shared_stage = Usd.Stage.Open(str(server / shared_result["subfolder"] / shared_result["name"]))
                    shared_mesh = UsdGeom.Mesh(shared_stage.GetPrimAtPath("/Model"))
                    self.assertTrue(shared_mesh)
                    self.assertEqual(
                        shared_mesh.GetPrim().GetAttribute("texture").Get().resolvedPath, asset.resolvedPath
                    )
                for upload_call in api.upload_file.await_args_list:
                    if pathlib.Path(upload_call.args[0]).suffix == ".usda":
                        self.assertFalse(pathlib.Path(upload_call.args[0]).exists())

    async def test_upload_inputs_dispatches_semantics_to_job_scoped_folders(self):
        """Textures upload with DDS conversion, meshes without, each source once in its own folder under the job."""
        # Arrange
        texture_source = "C:/inputs/shared/source.dds"
        mesh_source = "C:/inputs/shared/source.glb"
        bindings = (
            ComfyUIInputBinding("1.inputs.image", RemixType.TEXTURE_FILE_PATH, texture_source),
            ComfyUIInputBinding("2.inputs.image", RemixType.TEXTURE_FILE_PATH, texture_source),
            ComfyUIInputBinding("3.inputs.model", RemixType.MESH_FILE_PATH, mesh_source),
        )
        request = _make_workflow_request(input_bindings=bindings)
        api = MagicMock()
        api.upload_file = AsyncMock(
            side_effect=lambda source, **_: {
                texture_source: {"name": "source.png", "subfolder": "texture-folder"},
                mesh_source: {"name": "source.glb", "subfolder": "mesh-folder"},
            }[source]
        )
        job = ComfyUIJob(job_id=uuid.UUID("12345678-1234-5678-1234-567812345678"))

        # Act
        uploaded = await job._upload_inputs(api, request)

        # Assert
        self.assertEqual(
            uploaded,
            {
                (RemixType.TEXTURE_FILE_PATH, texture_source): {
                    "name": "source.png",
                    "subfolder": "texture-folder",
                },
                (RemixType.MESH_FILE_PATH, mesh_source): {
                    "name": "source.glb",
                    "subfolder": "mesh-folder",
                },
            },
        )
        # Two bindings share one texture source: it uploads once.
        self.assertEqual(api.upload_file.await_count, 2)
        calls = {call.args[0]: call.kwargs for call in api.upload_file.await_args_list}
        self.assertTrue(calls[texture_source]["convert_dds"])
        self.assertFalse(calls[mesh_source]["convert_dds"])
        texture_folder = calls[texture_source]["subfolder"]
        mesh_folder = calls[mesh_source]["subfolder"]
        self.assertTrue(texture_folder.startswith("rtx-remix/12345678-1234-5678-1234-567812345678/inputs/"))
        self.assertTrue(mesh_folder.startswith("rtx-remix/12345678-1234-5678-1234-567812345678/inputs/"))
        self.assertNotEqual(texture_folder, mesh_folder)

    async def test_build_prompt_uses_semantic_upload_keys_and_keeps_request_unchanged(self):
        """Prompt construction writes each uploaded relative path to its bound port."""
        # Arrange
        texture_binding = ComfyUIInputBinding("1.inputs.image", RemixType.TEXTURE_FILE_PATH, "C:/inputs/albedo.dds")
        mesh_binding = ComfyUIInputBinding("2.inputs.model", RemixType.MESH_FILE_PATH, "C:/inputs/model.glb")
        request = _make_workflow_request(
            prompt={
                "1": {"inputs": {"image": "C:/inputs/albedo.dds"}},
                "2": {"inputs": {"model": "C:/inputs/model.glb"}},
            },
            input_bindings=(texture_binding, mesh_binding),
        )
        uploaded = {
            (texture_binding.remix_type, texture_binding.source): {
                "name": "albedo.png",
                "subfolder": "textures/hash",
            },
            (mesh_binding.remix_type, mesh_binding.source): {"name": "model.glb", "subfolder": "meshes/hash"},
        }
        job = ComfyUIJob()

        # Act
        prompt = job._build_prompt(request, uploaded)

        # Assert
        self.assertEqual(prompt["1"]["inputs"]["image"], "textures/hash/albedo.png")
        self.assertEqual(prompt["2"]["inputs"]["model"], "meshes/hash/model.glb")
        self.assertEqual(request.prompt["1"]["inputs"]["image"], "C:/inputs/albedo.dds")
        self.assertEqual(request.prompt["2"]["inputs"]["model"], "C:/inputs/model.glb")

    async def test_build_prompt_rejects_browser_viewer_rendered_inputs(self):
        """A Load3D-style input that points at viewer temp renders fails before submission with guidance."""
        # Arrange
        mesh_binding = ComfyUIInputBinding("197.inputs.model_file", RemixType.MESH_FILE_PATH, "C:/inputs/model.usda")
        request = _make_workflow_request(
            prompt={
                "197": {
                    "class_type": "Load3D",
                    "inputs": {
                        "model_file": "C:/inputs/model.usda",
                        "image": {"image": "threed/scene_1.png [temp]", "mask": "threed/mask_1.png [temp]"},
                    },
                }
            },
            input_bindings=(mesh_binding,),
        )
        uploaded = {(mesh_binding.remix_type, mesh_binding.source): {"name": "model.usda", "subfolder": "m"}}

        # Act / Assert
        with self.assertRaisesRegex(ViewerRenderedInputError, r"Load3D \(node 197\) input 'image'.*browser viewer"):
            ComfyUIJob()._build_prompt(request, uploaded)

    async def test_build_prompt_accepts_null_metadata(self):
        """Null or non-dictionary metadata does not change text inputs."""
        for invalid in (None, [], "untagged"):
            for metadata in (
                invalid,
                {"rtx-remix": invalid},
                {"rtx-remix": {"inputs": invalid}},
                {"rtx-remix": {"inputs": {"text": invalid}}},
            ):
                with self.subTest(metadata=metadata):
                    # Arrange
                    request = _make_workflow_request(
                        prompt={
                            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "plain text"}, "_meta": metadata}
                        }
                    )

                    # Act
                    prompt = ComfyUIJob()._build_prompt(request, {})

                    # Assert
                    self.assertEqual(prompt["2"]["inputs"]["text"], "plain text")

    async def test_build_prompt_rejects_load3d_viewer_image_with_null_metadata(self):
        """Loader validation rejects viewer files without metadata."""
        # Arrange
        request = _make_workflow_request(
            prompt={"197": {"class_type": "Load3D", "inputs": {"image": "scene_00001_.png [temp]"}, "_meta": None}}
        )

        # Act / Assert
        with self.assertRaises(ViewerRenderedInputError):
            ComfyUIJob()._build_prompt(request, {})

    async def test_build_prompt_rejects_load3d_viewer_image(self):
        """A Load3D image requires a server file rather than a browser render."""
        # Arrange
        request = _make_workflow_request(
            prompt={"197": {"class_type": "Load3D", "inputs": {"image": "scene_00001_.png [temp]"}}}
        )

        # Act / Assert
        with self.assertRaisesRegex(ViewerRenderedInputError, r"Load3D \(node 197\) input 'image'.*browser viewer"):
            ComfyUIJob()._build_prompt(request, {})

    async def test_build_prompt_keeps_file_like_free_text(self):
        """A file-like text value is not a file input."""
        # Arrange
        request = _make_workflow_request(
            prompt={"2": {"class_type": "CLIPTextEncode", "inputs": {"text": "scene.png [temp]"}}}
        )

        # Act
        prompt = ComfyUIJob()._build_prompt(request, {})

        # Assert
        self.assertEqual(prompt["2"]["inputs"]["text"], "scene.png [temp]")

    async def test_build_prompt_rejects_tagged_viewer_file(self):
        """A custom node file input cannot depend on browser renders."""
        # Arrange
        request = _make_workflow_request(
            prompt={
                "2": {
                    "class_type": "CustomNode",
                    "_meta": {"rtx-remix": {"inputs": {"source": {"remix_type": RemixType.TEXTURE_FILE_PATH.value}}}},
                    "inputs": {"source": ["scene.png [temp]"]},
                }
            }
        )

        # Act / Assert
        with self.assertRaisesRegex(ViewerRenderedInputError, r"CustomNode \(node 2\) input 'source'.*browser viewer"):
            ComfyUIJob()._build_prompt(request, {})

    async def test_build_prompt_keeps_remix_node_text_input(self):
        """A Remix node text input stays text even when it looks like a viewer file."""
        # Arrange
        request = _make_workflow_request(
            prompt={"2": {"class_type": "RTXRemixSomething", "inputs": {"text": "scene.png [temp]"}}}
        )

        # Act
        prompt = ComfyUIJob()._build_prompt(request, {})

        # Assert
        self.assertEqual(prompt["2"]["inputs"]["text"], "scene.png [temp]")

    async def test_build_prompt_rejects_remix_node_file_input_that_names_a_viewer_file(self):
        """A Remix node file input rejects browser renders."""
        # Arrange
        request = _make_workflow_request(
            prompt={
                "2": {
                    "class_type": "RTXRemixSomething",
                    "inputs": {"text": "scene.png [temp]", "mesh_file_path": "scene.glb [temp]"},
                }
            }
        )

        # Act / Assert
        with self.assertRaisesRegex(
            ViewerRenderedInputError, r"RTXRemixSomething \(node 2\) input 'mesh_file_path'.*browser viewer"
        ):
            ComfyUIJob()._build_prompt(request, {})

    async def test_build_prompt_keeps_free_text_that_ends_in_temp(self):
        """A prompt string that ends in ``[temp]`` is text, not a viewer file, and reaches the server unchanged."""
        # Arrange
        mesh_binding = ComfyUIInputBinding("1.inputs.model_file", RemixType.MESH_FILE_PATH, "C:/inputs/model.usda")
        request = _make_workflow_request(
            prompt={
                "1": {"class_type": "Load3D", "inputs": {"model_file": "C:/inputs/model.usda"}},
                "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "rusty metal plate [temp]"}},
            },
            input_bindings=(mesh_binding,),
        )
        uploaded = {(mesh_binding.remix_type, mesh_binding.source): {"name": "model.usda", "subfolder": "m"}}

        # Act
        prompt = ComfyUIJob()._build_prompt(request, uploaded)

        # Assert
        self.assertEqual(prompt["2"]["inputs"]["text"], "rusty metal plate [temp]")

    async def test_execution_error_names_failing_node(self):
        """A ComfyUI node failure reaches the user with the node and its message, not a connection error."""
        # Arrange
        error = ComfyUIExecutionError(
            "p1",
            {"node_id": "197", "node_type": "Load3D", "exception_message": "[Errno 2] No such file\n"},
        )

        # Assert
        self.assertEqual(
            error.user_message,
            "ComfyUI node Load3D (node 197) failed: [Errno 2] No such file. Fix the workflow in ComfyUI and try again.",
        )

    async def test_parse_results_reads_images_and_3d_channels_in_output_order(self):
        """The parser reads each semantic from its official history channel."""
        # Arrange
        workflow = Workflow(
            output_specs=[
                WorkflowOutput(
                    node_id="20",
                    remix_type=RemixType.MESH_FILE_PATH,
                    order=2,
                    apply_behavior=OutputApplyBehavior.APPEND,
                ),
                WorkflowOutput(
                    node_id="10",
                    remix_type=RemixType.TEXTURE_FILE_PATH,
                    order=1,
                    texture_type="normal_ogl",
                    apply_behavior=OutputApplyBehavior.NONE,
                ),
            ]
        )
        history = {
            "prompt-123": {
                "outputs": {
                    "10": {
                        "images": [
                            {"filename": "preview.png", "type": "temp"},
                            {"filename": "normal.png", "subfolder": "textures", "type": "output"},
                        ]
                    },
                    "20": {"3d": [{"filename": "model.glb", "subfolder": "models", "type": "output"}]},
                }
            }
        }
        job = ComfyUIJob()

        # Act
        results = job._parse_results(history, "prompt-123", workflow)

        # Assert
        self.assertEqual(
            results,
            [
                ComfyUIFileResult(
                    filename="normal.png",
                    key="10",
                    remix_type=RemixType.TEXTURE_FILE_PATH,
                    order=1,
                    subfolder="textures",
                    texture_type="normal_ogl",
                ),
                ComfyUIFileResult(
                    filename="model.glb",
                    key="20",
                    remix_type=RemixType.MESH_FILE_PATH,
                    order=2,
                    subfolder="models",
                ),
            ],
        )

    async def test_parse_results_rejects_missing_final_file_for_each_channel(self):
        """Each declared image or mesh output must have one final record."""
        cases = (
            (RemixType.TEXTURE_FILE_PATH, "albedo", "images", "3d"),
            (RemixType.MESH_FILE_PATH, None, "3d", "images"),
        )
        for remix_type, texture_type, expected_channel, wrong_channel in cases:
            with self.subTest(title=expected_channel):
                # Arrange
                workflow = Workflow(
                    output_specs=[
                        WorkflowOutput(
                            node_id="10",
                            remix_type=remix_type,
                            texture_type=texture_type,
                            apply_behavior=(
                                OutputApplyBehavior.REPLACE
                                if remix_type is RemixType.TEXTURE_FILE_PATH
                                else OutputApplyBehavior.APPEND
                            ),
                        )
                    ]
                )
                history = {
                    "prompt-123": {"outputs": {"10": {wrong_channel: [{"filename": "wrong.bin", "type": "output"}]}}}
                }
                job = ComfyUIJob()

                # Act
                with self.assertRaisesRegex(RuntimeError, "did not produce a final file") as error_context:
                    job._parse_results(history, "prompt-123", workflow)

                # Assert
                self.assertIn(texture_type or "mesh", str(error_context.exception))

    async def test_parse_results_rejects_multiple_final_files_for_each_channel(self):
        """Each declared image or mesh output rejects more than one final record."""
        cases = (
            (RemixType.TEXTURE_FILE_PATH, "albedo", "images"),
            (RemixType.MESH_FILE_PATH, None, "3d"),
        )
        for remix_type, texture_type, channel in cases:
            with self.subTest(title=channel):
                # Arrange
                workflow = Workflow(
                    output_specs=[
                        WorkflowOutput(
                            node_id="10",
                            remix_type=remix_type,
                            texture_type=texture_type,
                            apply_behavior=(
                                OutputApplyBehavior.REPLACE
                                if remix_type is RemixType.TEXTURE_FILE_PATH
                                else OutputApplyBehavior.APPEND
                            ),
                        )
                    ]
                )
                history = {
                    "prompt-123": {
                        "outputs": {
                            "10": {
                                channel: [
                                    {"filename": "first.bin", "type": "output"},
                                    {"filename": "second.bin", "type": "output"},
                                ]
                            }
                        }
                    }
                }
                job = ComfyUIJob()

                # Act
                with self.assertRaisesRegex(RuntimeError, "multiple final files") as error_context:
                    job._parse_results(history, "prompt-123", workflow)

                # Assert
                self.assertIn("exactly one is required", str(error_context.exception))

    async def test_parse_results_rejects_unsafe_server_path(self):
        """The parser rejects a server path that can escape the output directory."""
        # Arrange
        workflow = Workflow(
            output_specs=[
                WorkflowOutput(
                    node_id="10",
                    remix_type=RemixType.MESH_FILE_PATH,
                    apply_behavior=OutputApplyBehavior.APPEND,
                )
            ]
        )
        history = {
            "prompt-123": {
                "outputs": {"10": {"3d": [{"filename": "model.glb", "subfolder": "../escape", "type": "output"}]}}
            }
        }
        job = ComfyUIJob()

        # Act
        with self.assertRaisesRegex(RuntimeError, "Invalid ComfyUI history response") as error_context:
            job._parse_results(history, "prompt-123", workflow)

        # Assert
        self.assertIsInstance(error_context.exception, RuntimeError)

    async def test_download_files_preserves_image_and_mesh_paths(self):
        """The downloader preserves server names and extensions for both channels."""
        # Arrange
        texture = ComfyUIFileResult(
            filename="albedo.png",
            key="10",
            remix_type=RemixType.TEXTURE_FILE_PATH,
            subfolder="textures",
            texture_type="albedo",
        )
        mesh = ComfyUIFileResult(
            filename="generated.glb",
            key="20",
            remix_type=RemixType.MESH_FILE_PATH,
            subfolder="models",
        )
        api = MagicMock()
        api.download_file = AsyncMock(side_effect=lambda _file, destination: destination)
        job = ComfyUIJob()

        # Act
        await job._download_files(api, [texture, mesh], "prompt-123", pathlib.Path("C:/jobs"))

        # Assert
        texture_destination = pathlib.Path("C:/jobs/outputs/prompt-123/textures/albedo.png")
        mesh_destination = pathlib.Path("C:/jobs/outputs/prompt-123/models/generated.glb")
        self.assertEqual(
            api.download_file.await_args_list,
            [call(texture, texture_destination), call(mesh, mesh_destination)],
        )
        self.assertEqual(texture.path, texture_destination)
        self.assertEqual(mesh.path, mesh_destination)

    async def test_download_files_rejects_duplicate_local_destination_before_download(self):
        """Two outputs cannot overwrite one queue artifact path."""
        # Arrange
        files = [
            ComfyUIFileResult(
                filename="output.png",
                key="10",
                remix_type=RemixType.TEXTURE_FILE_PATH,
                subfolder="same",
                texture_type="albedo",
            ),
            ComfyUIFileResult(
                filename="output.png",
                key="11",
                remix_type=RemixType.TEXTURE_FILE_PATH,
                subfolder="same",
                texture_type="roughness",
            ),
        ]
        api = MagicMock()
        api.download_file = AsyncMock()
        job = ComfyUIJob()

        # Act
        with self.assertRaisesRegex(RuntimeError, "same local artifact path") as error_context:
            await job._download_files(api, files, "prompt-123", pathlib.Path("C:/jobs"))

        # Assert
        self.assertIsInstance(error_context.exception, RuntimeError)
        api.download_file.assert_not_awaited()

    async def test_asset_execute_downloads_mesh_and_tagged_textures_in_one_request(self):
        """The asset request carries downloaded texture paths and one publication root."""
        # Arrange
        api = MagicMock()
        api.submit_prompt = AsyncMock(return_value="prompt-123")
        api.wait_for_prompt_completion = AsyncMock(
            return_value={
                "prompt-123": {
                    "outputs": {
                        "20": {"3d": [{"filename": "model.glb", "type": "output"}]},
                        "10": {"images": [{"filename": "albedo.png", "type": "output"}]},
                    }
                }
            }
        )
        api.download_file = AsyncMock(side_effect=lambda _file, destination: destination)
        request = _make_workflow_request(
            output_specs=(
                WorkflowOutput(node_id="20", remix_type=RemixType.MESH_FILE_PATH),
                WorkflowOutput(node_id="10", remix_type=RemixType.TEXTURE_FILE_PATH, texture_type="albedo"),
            ),
            output_url="omniverse://server/output",
        )
        job = ComfyUIAssetJob()

        # Act
        with patch.object(job_module, "ComfyUIAPI", return_value=api):
            outputs = await job.execute(
                pathlib.Path("C:/queue"), JobInputs({job.WORKFLOW_REQUEST: request}), AsyncMock()
            )

        # Assert
        self.assertEqual(tuple(outputs), (job.MESH_REQUEST,))
        self.assertEqual(
            outputs[job.MESH_REQUEST],
            MeshOptimizationRequest(
                source_path=pathlib.Path("C:/queue/outputs/prompt-123/model.glb"),
                source_root=pathlib.Path("C:/queue/outputs/prompt-123"),
                output_url="omniverse://server/output/asset",
                extra_textures=(
                    TextureOptimizationItem(
                        "10",
                        pathlib.Path("C:/queue/outputs/prompt-123/albedo.png"),
                        TextureTypes.DIFFUSE,
                    ),
                ),
            ),
        )

    async def test_asset_execute_requires_one_downloaded_mesh_and_supported_textures(self):
        """Invalid mesh counts, absent downloads, and unsupported texture types fail."""
        # Arrange
        mesh = ComfyUIFileResult(
            filename="model.glb", key="20", remix_type=RemixType.MESH_FILE_PATH, path=pathlib.Path("C:/queue/model.glb")
        )
        texture = ComfyUIFileResult(
            filename="albedo.png",
            key="10",
            remix_type=RemixType.TEXTURE_FILE_PATH,
            texture_type="albedo",
            path=pathlib.Path("C:/queue/albedo.png"),
        )
        texture.texture_type = "unsupported"
        for files in (
            [],
            [mesh, dataclasses.replace(mesh, key="21")],
            [dataclasses.replace(mesh, path=None)],
            [mesh, texture],
        ):
            with self.subTest(files=files):
                # Arrange
                job = ComfyUIAssetJob()
                generate_files = patch.object(
                    job, "_generate_files", AsyncMock(return_value=(files, pathlib.Path("C:/queue")))
                )

                # Act / Assert
                with generate_files, self.assertRaises(JobExecutionError):
                    await job.execute(
                        pathlib.Path("C:/queue"),
                        JobInputs({job.WORKFLOW_REQUEST: _make_workflow_request()}),
                        AsyncMock(),
                    )

    async def test_asset_execute_without_textures_keeps_queue_owned_output(self):
        """A mesh-only workflow does not require texture outputs or a publication URL."""
        # Arrange
        job = ComfyUIAssetJob()
        mesh = ComfyUIFileResult(
            filename="model.glb", key="20", remix_type=RemixType.MESH_FILE_PATH, path=pathlib.Path("C:/queue/model.glb")
        )

        # Act
        with patch.object(job, "_generate_files", AsyncMock(return_value=([mesh], pathlib.Path("C:/queue")))):
            outputs = await job.execute(
                pathlib.Path("C:/queue"),
                JobInputs({job.WORKFLOW_REQUEST: _make_workflow_request(output_url=None)}),
                AsyncMock(),
            )

        # Assert
        self.assertEqual(
            outputs[job.MESH_REQUEST],
            MeshOptimizationRequest(
                source_path=mesh.path,
                source_root=mesh.path.parent,
                output_url=None,
                extra_textures=(),
            ),
        )

    async def test_persistence_round_trips_generation_job_fields(self):
        """Both generation jobs preserve their saved server and target fields."""
        jobs = tuple(
            job_type(
                name="Generate",
                context_name="texturecraft",
                prim_paths=["/World/Mesh"],
                material_path="/World/Looks/Material",
                scheme="https",
                host="server",
                port=8189,
            )
            for job_type in (ComfyUIJob, ComfyUIAssetJob)
        )
        for expected in jobs:
            with self.subTest(title=expected.name):
                # Act
                restored = deserialize(serialize(expected))

                # Assert
                self.assertEqual(restored, expected)
                self.assertIs(type(restored), type(expected))

    async def test_persistence_round_trips_all_new_job_values(self):
        """New semantic, result, target, receipt, and setting values keep exact types."""
        reference = Sdf.Reference(
            assetPath="../source.glb",
            primPath=Sdf.Path("/Root"),
            layerOffset=Sdf.LayerOffset(2.0, 3.0),
            customData={"source": "test"},
        )
        metadata_receipt = MetadataApplyReceipt(
            prior_meta=((pathlib.Path("C:/published/albedo.dds.meta"), '{"prior": true}'),)
        )
        texture_receipt = ComfyUIApplyReceipt(
            original_authored_values=(("/Shader.inputs:diffuse_texture", "../old.dds"),),
            original_compare_values=(("/Shader.inputs:diffuse_texture", "C:/old.dds"),),
            applied_compare_values=(("/Shader.inputs:diffuse_texture", "C:/published/albedo.dds"),),
            metadata_receipt=metadata_receipt,
        )
        reference_target = ReferenceTarget(
            owner_prim_path="/World/Mesh",
            source_reference=reference,
            source_layer_identifier="C:/project/source.usda",
        )
        asset_target = _make_asset_target(
            reference_targets=(reference_target,),
            texture_targets=(("albedo", "/Shader.inputs:diffuse_texture"),),
            behavior=OutputApplyBehavior.REPLACE,
        )
        file_result = ComfyUIFileResult(
            filename="albedo.png",
            key="10",
            remix_type=RemixType.TEXTURE_FILE_PATH,
            order=1,
            texture_type="albedo",
            path=pathlib.Path("C:/queue/albedo.png"),
        )
        binding = ComfyUIInputBinding(
            port_id="1.inputs.image",
            remix_type=RemixType.TEXTURE_FILE_PATH,
            source="C:/inputs/albedo.dds",
        )
        workflow_request = _make_workflow_request(
            prompt={"1": {"inputs": {"image": binding.source}}},
            input_bindings=(binding,),
            output_specs=(
                WorkflowOutput(
                    node_id="10",
                    remix_type=RemixType.TEXTURE_FILE_PATH,
                    texture_type="albedo",
                    apply_behavior=OutputApplyBehavior.REPLACE,
                ),
            ),
        )
        values = (
            OutputApplyBehavior.APPEND,
            MeshReferenceSelection.SELECTED,
            reference,
            texture_receipt,
            reference_target,
            asset_target,
            binding,
            file_result,
            workflow_request,
        )
        for expected in values:
            with self.subTest(title=type(expected).__name__):
                # Arrange
                expected_type = type(expected)

                # Act
                restored = deserialize(serialize(expected))

                # Assert
                self.assertIs(type(restored), expected_type)
                self.assertEqual(restored, expected)

    async def test_legacy_apply_receipt_payload_decodes_with_empty_metadata(self):
        """The released three-value receipt retains its texture state and has no metadata to restore."""
        # Arrange
        path = "/Shader.inputs:diffuse_texture"
        receipt = ComfyUIApplyReceipt(
            original_authored_values=((path, "old.dds"),),
            original_compare_values=((path, "old.dds"),),
            applied_compare_values=((path, "applied.dds"),),
            metadata_receipt=MetadataApplyReceipt(prior_meta=()),
        )
        envelope = json.loads(serialize(receipt))
        envelope["value"]["value"] = envelope["value"]["value"][:3]  # Use the released payload shape.

        # Act
        legacy_receipt = deserialize(json.dumps(envelope))

        # Assert: the legacy payload decodes with an empty metadata receipt.
        self.assertEqual(legacy_receipt, receipt)
        self.assertEqual(legacy_receipt.metadata_receipt, MetadataApplyReceipt(prior_meta=()))

    async def test_legacy_texture_type_target_key_matches_the_one_texture_of_that_type(self):
        """A 3.0.5 target keyed by texture type applies to node-id keyed results while that type is unique.

        A ``normal_dx`` key matches the octahedral normal the pipeline converted it to.
        """
        # Arrange
        processed = _make_node_keyed_textures()
        roughness_path = "/Shader.inputs:reflectionroughness_texture"
        normal_path = "/Shader.inputs:normalmap_texture"

        # Act
        replacements = apply_handler_module._get_replacements(
            processed, (("roughness", roughness_path), ("normal_dx", normal_path))
        )

        # Assert
        self.assertEqual(
            replacements,
            ((roughness_path, "C:/published/roughness.dds"), (normal_path, "C:/published/normal_ogl.dds")),
        )

    async def test_legacy_normal_ogl_target_key_matches_the_converted_octahedral_normal(self):
        """A ``normal_ogl`` key matches the octahedral normal the pipeline converted it to."""
        # Arrange
        processed = _make_node_keyed_textures()
        normal_path = "/Shader.inputs:normalmap_texture"

        # Act
        replacements = apply_handler_module._get_replacements(processed, (("normal_ogl", normal_path),))

        # Assert
        self.assertEqual(replacements, ((normal_path, "C:/published/normal_ogl.dds"),))

    async def test_legacy_texture_type_target_key_without_that_texture_raises(self):
        """A texture type key that no processed texture carries fails the Replace."""
        # Arrange
        processed = _make_node_keyed_textures()

        # Act / Assert
        with self.assertRaisesRegex(ValueError, "did not produce every Replace"):
            apply_handler_module._get_replacements(processed, (("metallic", "/Shader.inputs:metallic_texture"),))

    async def test_legacy_texture_type_target_key_with_two_textures_of_that_type_raises(self):
        """A texture type key is ambiguous when two processed textures carry that type."""
        # Arrange
        processed = _make_node_keyed_textures()
        two_normals = dataclasses.replace(
            processed, items=processed.items + (dataclasses.replace(processed.items[1], key="13"),)
        )

        # Act / Assert
        with self.assertRaisesRegex(ValueError, "did not produce every Replace"):
            apply_handler_module._get_replacements(two_normals, (("normal_dx", "/Shader.inputs:normalmap_texture"),))

    async def test_apply_receipt_payload_arity_outside_legacy_and_current_shapes_raises(self):
        """A receipt payload with two values fails to decode."""
        # Arrange
        path = "/Shader.inputs:diffuse_texture"
        receipt = ComfyUIApplyReceipt(
            original_authored_values=((path, "old.dds"),),
            original_compare_values=((path, "old.dds"),),
            applied_compare_values=((path, "applied.dds"),),
            metadata_receipt=MetadataApplyReceipt(prior_meta=()),
        )
        envelope = json.loads(serialize(receipt))
        envelope["value"]["value"] = envelope["value"]["value"][:2]  # neither 3 nor 4 values

        # Act / Assert
        with self.assertRaises(ValueError):
            deserialize(json.dumps(envelope))

    async def test_texture_apply_failure_restores_metadata_attempt_and_reports_apply_error(self):
        """A texture write failure restores the sidecars captured for this attempt."""
        # Arrange
        path = "/Shader.inputs:diffuse_texture"
        value = _make_processed_textures("albedo")
        target = _make_texture_target((("albedo", path),))
        receipt = _make_texture_receipt(
            original=((path, "C:/old/albedo.dds"),),
            applied=((path, "C:/published/albedo.dds"),),
        )
        rollback_receipt = MetadataApplyReceipt(prior_meta=((pathlib.Path("C:/published/albedo.dds.meta"), "{}"),))
        replacements = MagicMock()
        replacements.replace_textures.side_effect = RuntimeError("stage write failed")
        revert = MagicMock()
        with (
            patch.object(apply_handler_module, "_get_apply_stage", return_value=(MagicMock(), MagicMock())),
            patch.object(apply_handler_module, "_verify_texture_receipt"),
            patch.object(apply_handler_module, "_texture_state", return_value="original"),
            patch.object(apply_handler_module, "capture_metadata_receipt", return_value=rollback_receipt),
            patch.object(apply_handler_module, "_write_output_metadata", AsyncMock()),
            patch.object(apply_handler_module, "revert_metadata", revert),
            patch.object(apply_handler_module, "TextureReplacementsCore", return_value=replacements),
        ):
            # Act
            with self.assertRaises(ApplyExecutionError) as error_context:
                await ComfyUITextureApplyHandler().apply(value, target, receipt)

        # Assert
        revert.assert_called_once_with(rollback_receipt)
        self.assertIsInstance(error_context.exception.diagnostic, RuntimeError)


class TestComfyUIAssetApplyHandler(AsyncTestCase):
    """Test the asset Apply handler's conflict checks and error recovery."""

    async def setUp(self) -> None:
        """Isolate metadata reads from the filesystem."""
        metadata_capture = patch.object(
            apply_handler_module, "capture_metadata_receipt", return_value=MetadataApplyReceipt(prior_meta=())
        )
        metadata_capture.start()
        self.addCleanup(metadata_capture.stop)

    async def test_asset_apply_failure_after_first_reference_undoes_the_partial_group(self):
        """A failure on the second owner undoes the reference added for the first owner."""
        # Arrange
        target = _make_asset_target(
            reference_targets=(
                ReferenceTarget("/World/AssetA", None, None),
                ReferenceTarget("/World/AssetB", None, None),
            ),
        )
        value = _make_mesh_result()
        receipt = _make_texture_receipt()
        stage = MagicMock()
        setup = MagicMock()
        setup.add_new_reference.side_effect = [
            (Sdf.Reference("./generated.glb"), "/World/AssetA/ref"),
            ValueError("no owner"),
        ]
        stack = []
        undo = MagicMock()
        with (
            patch.object(apply_handler_module, "_get_apply_stage", return_value=(stage, MagicMock())),
            patch.object(apply_handler_module, "_reference_state", return_value=("original", {})),
            patch.object(apply_handler_module, "_write_output_metadata", AsyncMock()),
            patch.object(apply_handler_module, "revert_metadata"),
            patch.object(apply_handler_module, "Setup", return_value=setup),
            patch.object(apply_handler_module.Usd, "EditContext"),
            patch.object(apply_handler_module.omni.kit.commands, "execute") as execute,
            patch.object(apply_handler_module.omni.kit.undo, "group") as group,
            patch.object(apply_handler_module.omni.kit.undo, "get_undo_stack", side_effect=lambda: stack),
            patch.object(apply_handler_module.omni.kit.undo, "undo", undo),
        ):
            group.return_value.__enter__.side_effect = lambda: stack.append("Group")

            # Act
            with self.assertRaises(ApplyExecutionError):
                await ComfyUIAssetApplyHandler().apply(value, target, receipt)

        # Assert
        self.assertEqual(setup.add_new_reference.call_count, 2)
        execute.assert_called_once_with(
            "CreateUsdAttribute",
            prim=stage.GetPrimAtPath.return_value,
            attr_name=apply_handler_module._GENERATED_FOR_ATTR,
            attr_type=Sdf.ValueTypeNames.String,
            attr_value=apply_handler_module._generated_marker("/World/AssetA", value.asset_url),
        )
        undo.assert_called_once_with()

    async def test_asset_apply_rejects_missing_owner_as_external_edit_before_writing_anything(self):
        """An owner prim that no longer exists is an external edit. No sidecar or stage write runs."""
        # Arrange
        target = _make_asset_target(reference_targets=(ReferenceTarget("/World/Asset", None, None),))
        value = _make_mesh_result()
        receipt = _make_texture_receipt()
        stage = MagicMock()
        stage.GetPrimAtPath.return_value.IsValid.return_value = False
        with (
            patch.object(apply_handler_module, "_get_apply_stage", return_value=(stage, MagicMock())),
            patch.object(apply_handler_module, "_write_output_metadata", AsyncMock()) as write_metadata,
            patch.object(apply_handler_module, "Setup") as setup,
        ):
            # Act
            with self.assertRaises(ApplyExecutionError) as error_context:
                await ComfyUIAssetApplyHandler().apply(value, target, receipt)

        # Assert
        self.assertIn("changed outside", error_context.exception.reason)
        write_metadata.assert_not_called()
        setup.assert_not_called()

    async def test_asset_revert_rejects_applied_replace_whose_owner_still_composes_the_source(self):
        """An applied Replace owner that still composes the removed source reference is an external edit."""
        # Arrange
        source_layer = Sdf.Layer.CreateAnonymous()
        source_url = "C:/project/source.usda"
        target = _make_asset_target(
            reference_targets=(
                ReferenceTarget("/World/Asset", Sdf.Reference(source_url), str(source_layer.identifier)),
            ),
            behavior=OutputApplyBehavior.REPLACE,
        )
        value = _make_mesh_result()
        receipt = _make_texture_receipt()
        child = MagicMock()
        stage = MagicMock()
        # The owner is a mesh prim, not a Remix reference child: Replace classifies it by its generated children.
        stage.GetPrimAtPath.return_value.GetAttribute.return_value.Get.return_value = None
        with (
            patch.object(apply_handler_module, "_get_apply_stage", return_value=(stage, MagicMock())),
            patch.object(apply_handler_module, "_generated_children", return_value=[child]),
            patch.object(apply_handler_module, "_source_composed", return_value=True),
            patch.object(apply_handler_module, "revert_metadata") as revert,
            patch.object(apply_handler_module.omni.kit.commands, "execute") as execute,
        ):
            # Act
            with self.assertRaises(ApplyExecutionError) as error_context:
                await ComfyUIAssetApplyHandler().revert(value, target, receipt)

        # Assert
        self.assertIn("changed outside", error_context.exception.reason)
        revert.assert_not_called()
        execute.assert_not_called()

    async def test_asset_apply_rejects_target_changed_during_sidecar_write_and_restores_sidecars(self):
        """A target that changes while sidecars are written is an external edit. Nothing mutates the stage."""
        # Arrange
        target = _make_asset_target(reference_targets=(ReferenceTarget("/World/Asset", None, None),))
        value = _make_mesh_result()
        receipt = _make_texture_receipt()
        rollback_receipt = MetadataApplyReceipt(prior_meta=((pathlib.Path("C:/published/generated.glb.meta"), "{}"),))
        with (
            patch.object(apply_handler_module, "_get_apply_stage", return_value=(MagicMock(), MagicMock())),
            patch.object(
                apply_handler_module,
                "_reference_state",
                side_effect=[("original", {}), ("applied", {"/World/Asset": [MagicMock()]})],
            ),
            patch.object(apply_handler_module, "capture_metadata_receipt", return_value=rollback_receipt),
            patch.object(apply_handler_module, "_write_output_metadata", AsyncMock()),
            patch.object(apply_handler_module, "revert_metadata") as revert,
            patch.object(apply_handler_module, "Setup") as setup,
        ):
            # Act
            with self.assertRaises(ApplyExecutionError) as error_context:
                await ComfyUIAssetApplyHandler().apply(value, target, receipt)

        # Assert
        self.assertIn("changed outside", error_context.exception.reason)
        revert.assert_called_once_with(rollback_receipt)
        setup.assert_not_called()

    async def test_asset_revert_whose_sidecar_restore_fails_reapplies_sidecars_and_leaves_the_stage_untouched(self):
        """A sidecar restore that fails part way re-applies the pre-attempt sidecars and never touches the stage."""
        # Arrange
        target = _make_asset_target(reference_targets=(ReferenceTarget("/World/Asset", None, None),))
        value = _make_mesh_result()
        receipt = _make_texture_receipt()
        rollback = MagicMock(name="attempt_rollback")
        with (
            patch.object(apply_handler_module, "_get_apply_stage", return_value=(MagicMock(), MagicMock())),
            patch.object(
                apply_handler_module, "_reference_state", return_value=("applied", {"/World/Asset": [MagicMock()]})
            ),
            patch.object(apply_handler_module, "capture_metadata_receipt", return_value=rollback),
            patch.object(
                apply_handler_module, "revert_metadata", side_effect=[OSError("second sidecar is locked"), None]
            ) as revert_metadata,
            patch.object(apply_handler_module.omni.kit.commands, "execute") as execute,
            patch.object(apply_handler_module, "TextureReplacementsCore") as replacements,
        ):
            # Act
            with self.assertRaises(ApplyExecutionError) as error_context:
                await ComfyUIAssetApplyHandler().revert(value, target, receipt)

        # Assert
        self.assertIsInstance(error_context.exception.__cause__, OSError)
        self.assertEqual(
            [call.args for call in revert_metadata.call_args_list], [(receipt.metadata_receipt,), (rollback,)]
        )
        execute.assert_not_called()
        replacements.assert_not_called()

    async def test_asset_revert_rejects_target_changed_during_sidecar_restore_and_reapplies_sidecars(self):
        """A target edited while sidecars are restored is an external edit. The sidecars go back to the applied state."""
        # Arrange
        target = _make_asset_target(reference_targets=(ReferenceTarget("/World/Asset", None, None),))
        value = _make_mesh_result()
        receipt = _make_texture_receipt()
        applied = ("applied", {"/World/Asset": [MagicMock()]})
        rollback = MagicMock(name="attempt_rollback")
        with (
            patch.object(apply_handler_module, "_get_apply_stage", return_value=(MagicMock(), MagicMock())),
            patch.object(apply_handler_module, "_reference_state", side_effect=[applied, ("original", {})]),
            patch.object(apply_handler_module, "capture_metadata_receipt", return_value=rollback),
            patch.object(apply_handler_module, "revert_metadata") as revert_metadata,
            patch.object(apply_handler_module.omni.kit.commands, "execute") as execute,
            patch.object(apply_handler_module, "TextureReplacementsCore") as replacements,
        ):
            # Act
            with self.assertRaises(ApplyExecutionError) as error_context:
                await ComfyUIAssetApplyHandler().revert(value, target, receipt)

        # Assert
        self.assertIn("changed outside", error_context.exception.reason)
        self.assertEqual(revert_metadata.call_args_list[-1].args, (rollback,))
        execute.assert_not_called()
        replacements.assert_not_called()

    async def test_asset_revert_rejects_stage_changed_during_sidecar_restore_and_reapplies_sidecars(self):
        """A stage change during sidecar restore prevents commands and restores the applied sidecars."""
        # Arrange
        target = _make_asset_target(reference_targets=(ReferenceTarget("/World/Asset", None, None),))
        value = _make_mesh_result()
        receipt = _make_texture_receipt()
        layer = MagicMock()
        rollback = MagicMock(name="attempt_rollback")
        with (
            patch.object(
                apply_handler_module, "_get_apply_stage", side_effect=[(MagicMock(), layer), (MagicMock(), layer)]
            ),
            patch.object(
                apply_handler_module, "_reference_state", return_value=("applied", {"/World/Asset": [MagicMock()]})
            ),
            patch.object(apply_handler_module, "capture_metadata_receipt", return_value=rollback),
            patch.object(apply_handler_module, "revert_metadata") as revert_metadata,
            patch.object(apply_handler_module.omni.kit.commands, "execute") as execute,
        ):
            # Act
            with self.assertRaises(ApplyExecutionError) as error_context:
                await ComfyUIAssetApplyHandler().revert(value, target, receipt)

        # Assert
        self.assertIn("changed outside", error_context.exception.reason)
        self.assertEqual(
            [call.args for call in revert_metadata.call_args_list], [(receipt.metadata_receipt,), (rollback,)]
        )
        execute.assert_not_called()
