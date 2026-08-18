"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

from __future__ import annotations

import asyncio
import pathlib
import tempfile
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import omni.usd
from lightspeed.trex.asset_pipeline.core.job import TextureProcessingJob
from lightspeed.trex.comfyui.core.api import ComfyUIAPI
from lightspeed.trex.comfyui.core.connection import set_connected_endpoint
from lightspeed.trex.comfyui.core.core import ComfyUICore
from lightspeed.trex.comfyui.core.enums import RemixType
from lightspeed.trex.comfyui.core.apply_handler import ComfyUIJobApplyHandler
from lightspeed.trex.comfyui.core.job import ComfyUIJob
from lightspeed.trex.comfyui.core.models import ComfyUIWorkflowRequest, Workflow, WorkflowInput, WorkflowOutput
from lightspeed.trex.comfyui.core.resolvers import SelectedTextureResolver
from lightspeed.trex.comfyui.widget.display_adapter import ComfyUIDisplayAdapter
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni import ui
from omni.flux.job_queue.core.apply_executor import ApplyExecutor
from omni.flux.job_queue.core.apply_handler_registry import ApplyHandlerRegistry
from omni.flux.job_queue.core.enums import ApplyDisposition, ApplyOperation, JobState
from omni.flux.job_queue.core.errors import ApplyExecutionError
from omni.flux.job_queue.core.execute import JobScheduler
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.job import JobGraph
from omni.flux.job_queue.widget.widget import QueueWidget
from omni.flux.utils.widget.resources import get_icons
from omni.kit.test import AsyncTestCase
from omni.kit import ui_test
from PIL import Image
from pxr import Sdf, UsdGeom, UsdShade

__all__ = ("TestTypedComfyUIProductWorkflowE2E",)

_CONTEXT_NAME = "comfyui_typed_product_e2e"
_CONNECTED_ENDPOINT = ("http", "127.0.0.1", 8188)
_RETARGET_ENDPOINT = ("https", "replacement.example.com", 443)


class TestTypedComfyUIProductWorkflowE2E(AsyncTestCase):
    """Exercise product-created ComfyUI graphs through the real typed scheduler."""

    async def setUp(self) -> None:
        """Create a saved two-material USD project and isolated durable queue."""
        self._context = omni.usd.get_context(_CONTEXT_NAME) or omni.usd.create_context(_CONTEXT_NAME)
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()
        self._temporary_directory = tempfile.TemporaryDirectory(prefix="comfyui-product-e2e-")
        self._temporary_path = pathlib.Path(self._temporary_directory.name)
        project_layer = Sdf.Layer.CreateNew(str(self._temporary_path / "project.usda"))
        await self._context.open_stage_async(project_layer.identifier)
        self._stage = self._context.get_stage()
        self._mesh_paths = self._create_materials(2)
        self._stage.GetRootLayer().Save()
        self._core = ComfyUICore(_CONTEXT_NAME)
        self._interface = QueueInterface(str(self._temporary_path / "queue.sqlite"))
        self._scheduler: JobScheduler | None = None
        set_connected_endpoint(_CONTEXT_NAME, None)

    async def tearDown(self) -> None:
        """Settle scheduling and release the queue, core, stage, and temporary files."""
        if self._scheduler is not None:
            await self._scheduler.stop()
        self._core.destroy()
        set_connected_endpoint(_CONTEXT_NAME, None)
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()
        omni.usd.destroy_context(_CONTEXT_NAME)
        self._temporary_directory.cleanup()

    def _create_materials(self, count: int) -> list[str]:
        """Create bound materials with one replaceable diffuse texture each.

        Args:
            count: Number of material and mesh pairs to create.

        Returns:
            Mesh paths suitable for public ComfyUI job preparation.
        """
        original_texture = self._temporary_path / "original.dds"
        original_texture.touch()
        mesh_paths = []
        for index in range(1, count + 1):
            material = UsdShade.Material.Define(self._stage, f"/World/Looks/Material{index}")
            shader = UsdShade.Shader.Define(self._stage, f"/World/Looks/Material{index}/Shader")
            shader.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(str(original_texture)))
            shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
            mesh = UsdGeom.Mesh.Define(self._stage, f"/World/Mesh{index}")
            UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
            mesh_paths.append(str(mesh.GetPath()))
        return mesh_paths

    @staticmethod
    def _workflow(*, missing_normal_input: bool = False) -> Workflow:
        """Create the one-output workflow used by product graph preparation.

        Args:
            missing_normal_input: Whether to require an unavailable selected normal texture.

        Returns:
            Persistable ComfyUI workflow.
        """
        inputs = []
        prompt = {"99": {"inputs": {}}}
        if missing_normal_input:
            prompt["1"] = {"inputs": {"image": ""}}
            inputs.append(
                WorkflowInput(
                    port_id="1.inputs.image",
                    label="Normal input",
                    native_type=pathlib.Path,
                    default_value=pathlib.Path(),
                    value=SelectedTextureResolver(TextureTypes.NORMAL_OGL, _CONTEXT_NAME),
                    remix_type=RemixType.TEXTURE_FILE_PATH,
                )
            )
        return Workflow(
            api=prompt,
            name="Generate diffuse",
            inputs=inputs,
            output_specs=[WorkflowOutput("99", "albedo")],
        )

    async def _prepare_graphs(self, prim_paths: list[str], workflow: Workflow) -> list:
        """Prepare product graphs through public connection and preparation APIs.

        Args:
            prim_paths: Selected material-owner paths.
            workflow: Active workflow to persist on generation jobs.

        Returns:
            Product-created typed job graphs.
        """
        with (
            patch.object(ComfyUIAPI, "ping", new=AsyncMock()),
            patch.object(ComfyUIAPI, "get_workflow_list", new=AsyncMock(return_value=[])),
        ):
            await self._core.connect()
        self._core.set_workflow(workflow)
        return list((await self._core.prepare_submission(prim_paths)).graphs)

    async def _run_overlap_scenario(self, graphs: list) -> dict[str, object]:
        """Run two product graphs through controlled server and pipeline boundaries.

        Args:
            graphs: Product-created two-stage material graphs.

        Returns:
            Observed concurrency, dependency, capacity, and Apply evidence.
        """
        first_generation_started = asyncio.Event()
        first_generation_release = asyncio.Event()
        second_generation_started = asyncio.Event()
        overlap_release = asyncio.Event()
        first_processing_started = asyncio.Event()
        second_processing_started = asyncio.Event()
        prompt_count = 0
        processing_count = 0
        processing_sources: list[tuple[pathlib.Path, ...]] = []

        async def submit_prompt(*_args, **_kwargs) -> str:
            """Assign deterministic prompt identifiers in submission order."""
            nonlocal prompt_count
            prompt_count += 1
            return f"prompt-{prompt_count}"

        async def wait_for_prompt(_api: ComfyUIAPI, prompt_id: str, _timeout: float) -> dict:
            """Gate each controlled server generation at the requested overlap point."""
            if prompt_id == "prompt-1":
                first_generation_started.set()
                await first_generation_release.wait()
            else:
                second_generation_started.set()
                await overlap_release.wait()
            return {
                prompt_id: {
                    "outputs": {"99": {"images": [{"filename": f"{prompt_id}.png", "subfolder": "", "type": "output"}]}}
                }
            }

        async def download_image(_api: ComfyUIAPI, _image, destination: pathlib.Path) -> pathlib.Path:
            """Materialize one controlled server output in its queue-owned directory."""
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"generated")
            return destination

        async def run_pipeline(config, context, *, on_step_started: object, on_item_completed) -> None:
            """Publish deterministic DDS files while exposing pipeline overlap signals."""
            del on_step_started
            nonlocal processing_count
            processing_count += 1
            current = processing_count
            processing_sources.append(tuple(item.source_path for item in context.items))
            if current == 1:
                first_processing_started.set()
                await overlap_release.wait()
            else:
                second_processing_started.set()
            config.output_dir.mkdir(parents=True, exist_ok=True)
            total = len(context.items)
            for index, item in enumerate(context.items, start=1):
                output = config.output_dir / f"{item.source_path.stem}.dds"
                output.write_bytes(b"processed")
                item.textures[0].path = output
                await on_item_completed(item, index, total)

        handles = [self._interface.submit(graph) for graph in graphs]
        generation_jobs = [graph.jobs[0] for graph in graphs]
        processing_jobs = [graph.jobs[1] for graph in graphs]
        with (
            patch.object(ComfyUIAPI, "submit_prompt", new=submit_prompt),
            patch.object(ComfyUIAPI, "wait_for_prompt_completion", new=wait_for_prompt),
            patch.object(ComfyUIAPI, "download_image", new=download_image),
            patch(
                "lightspeed.trex.asset_pipeline.core.job.run_remix_asset_pipeline",
                new=run_pipeline,
            ),
        ):
            self._scheduler = JobScheduler(self._interface)
            self._scheduler.start()
            await asyncio.wait_for(first_generation_started.wait(), 2)
            second_started_before_release = second_generation_started.is_set()
            first_generation_release.set()
            await asyncio.wait_for(first_processing_started.wait(), 2)
            await asyncio.wait_for(second_generation_started.wait(), 2)
            overlap_snapshots = {
                job.job_id: self._interface.get_job_snapshot(job.job_id) for job in (*generation_jobs, *processing_jobs)
            }
            second_processing_started_during_first = second_processing_started.is_set()
            overlap_release.set()
            await asyncio.gather(*(handle.outputs(10) for group in handles for handle in group))
            await self._scheduler.stop()
            self._scheduler = None

        return {
            "second_started_before_release": second_started_before_release,
            "second_processing_started_during_first": second_processing_started_during_first,
            "overlap_snapshots": overlap_snapshots,
            "processing_sources": processing_sources,
            "final_processing": [self._interface.get_job_snapshot(job.job_id) for job in processing_jobs],
        }

    async def test_product_graphs_overlap_exact_types_and_gate_apply_on_processed_output(self) -> None:
        """Generation and processing overlap across exact one-worker lanes with typed dependency flow."""
        # Resolve two selected materials into independent generation-to-processing graphs.
        graphs = await self._prepare_graphs(self._mesh_paths, self._workflow())
        generation_jobs = [graph.jobs[0] for graph in graphs]
        processing_jobs = [graph.jobs[1] for graph in graphs]

        # Hold each real lane at controlled boundaries so their overlap can be observed without timing guesses.
        evidence = await self._run_overlap_scenario(graphs)

        # Each exact type remains serial while generation and processing from different graphs overlap.
        self.assertEqual(len(graphs), 2)
        self.assertTrue(all(len(graph.jobs) == 2 for graph in graphs))
        self.assertTrue(all(type(job) is ComfyUIJob for job in generation_jobs))
        self.assertTrue(all(type(job) is TextureProcessingJob for job in processing_jobs))
        self.assertFalse(evidence["second_started_before_release"])
        self.assertFalse(evidence["second_processing_started_during_first"])
        snapshots = evidence["overlap_snapshots"]
        self.assertIs(snapshots[generation_jobs[1].job_id].state, JobState.IN_PROGRESS)
        self.assertIs(snapshots[processing_jobs[0].job_id].state, JobState.IN_PROGRESS)
        self.assertIs(snapshots[processing_jobs[1].job_id].state, JobState.WAITING_FOR_DEPENDENCIES)
        self.assertIs(snapshots[processing_jobs[0].job_id].apply_disposition, ApplyDisposition.NOT_READY)
        self.assertTrue(all(path.exists() for sources in evidence["processing_sources"] for path in sources))
        self.assertTrue(
            all(snapshot.apply_disposition is ApplyDisposition.PENDING for snapshot in evidence["final_processing"])
        )

    async def test_generated_pbr_images_process_without_project_then_apply_after_reopen(self) -> None:
        """Long-running generation and processing finish project-free before a fast USD Apply."""
        shader = UsdShade.Shader(self._stage.GetPrimAtPath("/World/Looks/Material1/Shader"))
        source_path = self._temporary_path / "source.png"
        source_image = Image.new("RGB", (16, 16), (64, 128, 255))
        source_image.save(source_path)
        texture_targets = {
            "albedo": "diffuse_texture",
            "roughness": "reflectionroughness_texture",
            "height": "height_texture",
            "normal_ogl": "normalmap_texture",
        }
        for input_name in texture_targets.values():
            shader.CreateInput(input_name, Sdf.ValueTypeNames.Asset).Set(
                Sdf.AssetPath(str(self._temporary_path / f"original-{input_name}.dds"))
            )
        shader.GetInput("diffuse_texture").Set(Sdf.AssetPath(str(source_path)))
        self._stage.GetRootLayer().Save()
        workflow = Workflow(
            api={
                "1": {"inputs": {"image": ""}},
                **{node_id: {"inputs": {}} for node_id in ("10", "11", "12", "13")},
            },
            name="Generate PBR textures",
            inputs=[
                WorkflowInput(
                    port_id="1.inputs.image",
                    label="Source texture",
                    native_type=pathlib.Path,
                    default_value=pathlib.Path(),
                    value=SelectedTextureResolver(TextureTypes.DIFFUSE, _CONTEXT_NAME),
                    remix_type=RemixType.TEXTURE_FILE_PATH,
                )
            ],
            output_specs=[
                WorkflowOutput("10", "albedo", 0),
                WorkflowOutput("11", "roughness", 1),
                WorkflowOutput("12", "height", 2),
                WorkflowOutput("13", "normal_ogl", 3),
            ],
        )
        graph = (await self._prepare_graphs(self._mesh_paths[:1], workflow))[0]
        generation_job, processing_job = graph.jobs
        queue_jobs = self._interface.submit(graph)
        project_path = str(self._stage.GetRootLayer().identifier)

        # Close the submitted project before any expensive work begins; queued jobs retain every required input.
        await self._context.close_stage_async()
        self._stage = None

        # Derive four deterministic PBR outputs from one source image, matching one ComfyUI multi-output response.
        red, green, blue = source_image.split()
        generated_images = {
            "albedo.png": source_image,
            "roughness.png": red,
            "height.png": green,
            "normal_ogl.png": Image.merge("RGB", (red, green, blue)),
        }

        async def download_image(_api: ComfyUIAPI, image, destination: pathlib.Path) -> pathlib.Path:
            destination.parent.mkdir(parents=True, exist_ok=True)
            generated_images[image.filename].save(destination)
            return destination

        history = {
            "pbr-prompt": {
                "outputs": {
                    node_id: {"images": [{"filename": filename, "subfolder": "", "type": "output"}]}
                    for node_id, filename in zip(
                        ("10", "11", "12", "13"),
                        generated_images,
                    )
                }
            }
        }
        upload_image = AsyncMock(return_value={"name": source_path.name, "subfolder": "uploaded"})
        apply_registry = ApplyHandlerRegistry()
        apply_registry.register_plugins([ComfyUIJobApplyHandler])
        apply_executor = ApplyExecutor(self._interface, apply_registry, auto_apply_enabled=lambda: True)
        with (
            patch.object(ComfyUIAPI, "upload_image", new=upload_image),
            patch.object(ComfyUIAPI, "submit_prompt", new=AsyncMock(return_value="pbr-prompt")),
            patch.object(ComfyUIAPI, "wait_for_prompt_completion", new=AsyncMock(return_value=history)),
            patch.object(ComfyUIAPI, "download_image", new=download_image),
        ):
            # Run generation and the connected real texture-processing job while no interactive project is open.
            self._scheduler = JobScheduler(self._interface)
            self._scheduler.start()
            await asyncio.gather(*(queue_job.outputs(120) for queue_job in queue_jobs))
            await self._scheduler.stop()
            self._scheduler = None
            await apply_executor.wait_idle()

        # Processing publishes the complete PBR set before the job becomes Apply-ready.
        processed_result = self._interface.get_job_outputs(processing_job.job_id)[
            TextureProcessingJob.PROCESSED_TEXTURES
        ]
        self.assertEqual(len(processed_result.items), 4)
        normal_result = next(item for item in processed_result.items if item.key == "normal_ogl")
        self.assertIs(normal_result.texture_type, TextureTypes.NORMAL_OTH)
        upload_image.assert_awaited_once()
        self.assertIsNone(self._context.get_stage())
        waiting_snapshot = self._interface.get_job_snapshot(processing_job.job_id)
        self.assertIs(waiting_snapshot.apply_disposition, ApplyDisposition.PENDING)
        self.assertIs(waiting_snapshot.apply_operation, ApplyOperation.IDLE)
        self.assertIsNone(waiting_snapshot.apply_error)

        # Open a different live project and prove Apply refuses to write there without changing the pending state.
        await self._context.new_stage_async()
        self._stage = self._context.get_stage()
        with self.assertRaises(ApplyExecutionError) as error_context:
            await apply_executor.apply(processing_job.job_id)
        self.assertEqual(
            error_context.exception.reason,
            "This job belongs to a different project. Open the project used to create it before applying its processed textures.\n"
            f"Job project: {project_path}\n"
            f"Opened project: {self._stage.GetRootLayer().identifier}",
        )
        wrong_project_snapshot = self._interface.get_job_snapshot(processing_job.job_id)
        self.assertIs(wrong_project_snapshot.apply_disposition, ApplyDisposition.PENDING)
        self.assertIs(wrong_project_snapshot.apply_operation, ApplyOperation.IDLE)
        self.assertIsNone(wrong_project_snapshot.apply_error)

        # Reopen the exact submitted project only after all expensive work and the safe refusal have completed.
        await self._context.close_stage_async()
        await self._context.open_stage_async(project_path)
        self._stage = self._context.get_stage()
        shader = UsdShade.Shader(self._stage.GetPrimAtPath("/World/Looks/Material1/Shader"))
        apply_block_reason = apply_executor.get_apply_block_reason(processing_job.job_id, ApplyOperation.APPLYING)
        self.assertIsNone(apply_block_reason, apply_block_reason)

        try:
            # Reconcile the pending handler that the stage-open integration targets, without rerunning expensive work.
            await apply_executor.reconcile(processing_job.job_id)
        finally:
            await apply_executor.shutdown()
            apply_registry.destroy()

        # Both stages remain Done and every authored material input resolves to its processed DDS output.
        snapshot = self._interface.get_job_snapshot(processing_job.job_id)
        failure = snapshot.apply_error.message if snapshot.apply_error is not None else snapshot.apply_reason
        self.assertIs(snapshot.apply_disposition, ApplyDisposition.APPLIED, failure)
        self.assertIs(self._interface.get_job_snapshot(generation_job.job_id).state, JobState.DONE)
        self.assertIs(snapshot.state, JobState.DONE)
        processed_by_key = {item.key: pathlib.Path(item.asset_url) for item in processed_result.items}
        for key, input_name in texture_targets.items():
            value = shader.GetInput(input_name).Get()
            self.assertIsInstance(value, Sdf.AssetPath)
            self.assertEqual(pathlib.Path(value.path).suffix, ".dds")
            self.assertTrue(pathlib.Path(value.resolvedPath).exists(), value.path)
            self.assertEqual(pathlib.Path(value.resolvedPath), processed_by_key[key])

    async def _run_retarget_scenario(self, graph) -> tuple:
        """Start a blocked scheduler and retarget its queued generation row through the adapter action."""
        generation_job = graph.jobs[0]
        processing_job = graph.jobs[1]
        handles = self._interface.submit(graph)
        set_connected_endpoint(_CONTEXT_NAME, None)
        waiting_reason = generation_job.get_schedule_block_reason()
        dialog_arguments = {}

        def capture_dialog(*_args, **kwargs) -> None:
            """Capture and confirm the row action without replacing queue behavior."""
            dialog_arguments.update(kwargs)

        async def download_image(_api: ComfyUIAPI, _image, destination: pathlib.Path) -> pathlib.Path:
            """Materialize the retargeted server output."""
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"generated")
            return destination

        async def run_pipeline(config, context, *, on_step_started: object, on_item_completed) -> None:
            """Publish one deterministic processed texture for the retargeted graph."""
            del on_step_started
            config.output_dir.mkdir(parents=True, exist_ok=True)
            for index, item in enumerate(context.items, start=1):
                output = config.output_dir / f"{item.source_path.stem}.dds"
                output.write_bytes(b"processed")
                item.textures[0].path = output
                await on_item_completed(item, index, len(context.items))

        with (
            patch("lightspeed.trex.comfyui.widget.display_adapter.get_comfyui_core_instance", return_value=self._core),
            patch("lightspeed.trex.comfyui.core.core.get_job_queue", return_value=self._interface),
            patch("lightspeed.trex.comfyui.widget.display_adapter._TrexMessageDialog", side_effect=capture_dialog),
            patch.object(ComfyUIAPI, "submit_prompt", new=AsyncMock(return_value="retargeted")),
            patch.object(
                ComfyUIAPI,
                "wait_for_prompt_completion",
                new=AsyncMock(
                    return_value={
                        "retargeted": {
                            "outputs": {"99": {"images": [{"filename": "retargeted.png", "type": "output"}]}}
                        }
                    }
                ),
            ),
            patch.object(ComfyUIAPI, "download_image", new=download_image),
            patch("lightspeed.trex.asset_pipeline.core.job.run_remix_asset_pipeline", new=run_pipeline),
        ):
            self._scheduler = JobScheduler(self._interface)
            self._scheduler.start()
            scheduler_cycle = asyncio.get_running_loop().create_future()
            asyncio.get_running_loop().call_soon(scheduler_cycle.set_result, None)
            await scheduler_cycle
            blocked_snapshot = self._interface.get_job_snapshot(generation_job.job_id)
            set_connected_endpoint(_CONTEXT_NAME, _RETARGET_ENDPOINT)
            adapter = ComfyUIDisplayAdapter()
            action = next(
                action
                for action in adapter.get_graph_actions(generation_job, _CONTEXT_NAME)
                if action.action_id == "retarget_comfyui"
            )
            adapter.execute_action(action.action_id, generation_job, _CONTEXT_NAME)
            dialog_arguments["ok_handler"]()
            await asyncio.gather(*(handle.outputs(10) for handle in handles))
            await self._scheduler.stop()
            self._scheduler = None
        updated_job = self._interface.get_job(generation_job.job_id)
        return (
            waiting_reason,
            blocked_snapshot,
            action,
            updated_job,
            self._interface.get_job_snapshot(processing_job.job_id),
        )

    async def test_disconnected_job_waits_and_row_action_retargets_only_queued_generation(self) -> None:
        """A saved endpoint block remains recoverable through the stable queue-row action."""
        # Submit against the saved endpoint, disconnect it, and exercise the rendered row-level Retarget flow.
        graph = (await self._prepare_graphs(self._mesh_paths[:1], self._workflow()))[0]

        waiting_reason, blocked_snapshot, action, updated_job, processing_snapshot = await self._run_retarget_scenario(
            graph
        )

        # Only the queued generation child changes endpoint; processing then consumes its completed output.
        self.assertIn("Connect to the ComfyUI server", waiting_reason)
        self.assertIs(blocked_snapshot.state, JobState.QUEUED)
        self.assertTrue(action.enabled)
        self.assertEqual(action.action_id, "retarget_comfyui")
        self.assertEqual((updated_job.scheme, updated_job.host, updated_job.port), _RETARGET_ENDPOINT)
        self.assertIs(self._interface.get_job_snapshot(updated_job.job_id).state, JobState.DONE)
        self.assertIs(processing_snapshot.state, JobState.DONE)
        self.assertIs(processing_snapshot.apply_disposition, ApplyDisposition.PENDING)

    async def test_disconnect_refreshes_graph_actions_and_uses_target_icon(self) -> None:
        """Disconnecting ComfyUI disables graph actions while Retarget keeps the MDI target icon."""
        generation_job = ComfyUIJob(
            context_name=_CONTEXT_NAME,
            scheme=_CONNECTED_ENDPOINT[0],
            host=_CONNECTED_ENDPOINT[1],
            port=_CONNECTED_ENDPOINT[2],
        )
        request = ComfyUIWorkflowRequest(
            prompt={},
            input_bindings=(),
            client_id="",
            timeout=300.0,
            output_url=str(self._temporary_path / "generated"),
            workflow=self._workflow(),
        )
        graph = JobGraph(name="Queue action state", jobs=[generation_job])
        graph.bind(generation_job, ComfyUIJob.WORKFLOW_REQUEST, request)
        self._interface.submit(graph)

        # Start connected so both graph actions initially have a valid server target.
        with patch("lightspeed.trex.comfyui.core.connection.get_job_queue", return_value=self._interface):
            set_connected_endpoint(_CONTEXT_NAME, _CONNECTED_ENDPOINT)
        apply_registry = ApplyHandlerRegistry()
        apply_executor = ApplyExecutor(self._interface, apply_registry)
        previous_setup_workspace = ComfyUIDisplayAdapter._setup_workspace
        previous_workflow_workspace = ComfyUIDisplayAdapter._workflow_workspace
        ComfyUIDisplayAdapter.set_workspaces(MagicMock(), MagicMock())
        window = ui.Window(f"ComfyUIQueueActionsE2E_{uuid.uuid4()}", width=1000, height=500)
        widget = None
        try:
            with (
                patch("lightspeed.trex.comfyui.widget.display_adapter.is_standalone", return_value=False),
                patch(
                    "lightspeed.trex.comfyui.widget.display_adapter.get_comfyui_core_instance",
                    return_value=self._core,
                ),
                patch("lightspeed.trex.comfyui.core.core.get_job_queue", return_value=self._interface),
            ):
                with window.frame:
                    widget = QueueWidget(self._interface, apply_executor, _CONTEXT_NAME)
                widget.show(True)
                await ui_test.human_delay()

                # Disconnect through the shared endpoint state while the real queue widget is visible.
                with patch("lightspeed.trex.comfyui.core.connection.get_job_queue", return_value=self._interface):
                    set_connected_endpoint(_CONTEXT_NAME, None)
                await ui_test.human_delay()

                # The existing rows update in place: server-dependent actions disable and Retarget keeps its MDI icon.
                open_workflow = ui_test.find(
                    f"{window.title}//Frame/**/Image[*].identifier=='open_workflow_graph_{graph.graph_id}_job_{generation_job.job_id}'"
                )
                retarget = ui_test.find(
                    f"{window.title}//Frame/**/Image[*].identifier=='retarget_comfyui_graph_{graph.graph_id}_job_{generation_job.job_id}'"
                )
                self.assertIsNotNone(open_workflow)
                self.assertIsNotNone(retarget)
                self.assertFalse(open_workflow.widget.enabled)
                self.assertFalse(retarget.widget.enabled)
                self.assertEqual(retarget.widget.name, "RetargetComfyUI")
                target_icon_path = pathlib.Path(get_icons("target"))
                self.assertTrue(target_icon_path.is_file())
                self.assertEqual(target_icon_path.name, "target.svg")
                self.assertEqual(
                    open_workflow.widget.tooltip,
                    "Connect to a ComfyUI server before opening this workflow.",
                )
        finally:
            if widget is not None:
                widget.destroy()
            window.destroy()
            await apply_executor.shutdown()
            apply_registry.destroy()
            ComfyUIDisplayAdapter.set_workspaces(previous_setup_workspace, previous_workflow_workspace)

    async def test_unavailable_product_actions_keep_the_complete_icon_set(self) -> None:
        """Unavailable product actions remain visible and disabled instead of shifting the action column."""
        # Submit one real ComfyUI-to-texture-processing graph before making its product service unavailable.
        graph = (await self._prepare_graphs(self._mesh_paths[:1], self._workflow()))[0]
        generation_job = next(job for job in graph.jobs if type(job) is ComfyUIJob)
        self._interface.submit(graph)

        apply_registry = ApplyHandlerRegistry()
        apply_executor = ApplyExecutor(self._interface, apply_registry)
        previous_setup_workspace = ComfyUIDisplayAdapter._setup_workspace
        previous_workflow_workspace = ComfyUIDisplayAdapter._workflow_workspace
        ComfyUIDisplayAdapter.set_workspaces(MagicMock(), MagicMock())
        window = ui.Window(f"ComfyUIUnavailableActionsE2E_{uuid.uuid4()}", width=1000, height=500)
        widget = None
        try:
            with (
                patch("lightspeed.trex.comfyui.widget.display_adapter.is_standalone", return_value=False),
                patch(
                    "lightspeed.trex.comfyui.widget.display_adapter.get_comfyui_core_instance",
                    side_effect=RuntimeError("ComfyUI is unavailable"),
                ),
            ):
                with window.frame:
                    widget = QueueWidget(self._interface, apply_executor, _CONTEXT_NAME)
                widget.show(True)
                await ui_test.human_delay()

                # Expand the real graph and verify every declared action retains its stable slot.
                branch = ui_test.find(f"{window.title}//Frame/**/Image[*].identifier=='queue_graph_branch'")
                self.assertIsNotNone(branch)
                await branch.click()
                await ui_test.human_delay()

                delete = ui_test.find(f"{window.title}//Frame/**/Image[*].identifier=='delete_graph_{graph.graph_id}'")
                focus = ui_test.find(
                    f"{window.title}//Frame/**/Image[*].identifier=='focus_in_viewport_graph_{graph.graph_id}_job_{generation_job.job_id}'"
                )
                open_workflow = ui_test.find(
                    f"{window.title}//Frame/**/Image[*].identifier=='open_workflow_graph_{graph.graph_id}_job_{generation_job.job_id}'"
                )
                retarget = ui_test.find(
                    f"{window.title}//Frame/**/Image[*].identifier=='retarget_comfyui_graph_{graph.graph_id}_job_{generation_job.job_id}'"
                )

                self.assertTrue(all(action is not None for action in (delete, focus, open_workflow, retarget)))
                self.assertFalse(open_workflow.widget.enabled)
                self.assertFalse(retarget.widget.enabled)
                self.assertEqual(
                    open_workflow.widget.tooltip,
                    "ComfyUI is unavailable, so this workflow cannot be opened.",
                )
                self.assertEqual(
                    retarget.widget.tooltip,
                    "ComfyUI is unavailable, so this graph cannot be retargeted.",
                )
        finally:
            if widget is not None:
                widget.destroy()
            window.destroy()
            await apply_executor.shutdown()
            apply_registry.destroy()
            ComfyUIDisplayAdapter.set_workspaces(previous_setup_workspace, previous_workflow_workspace)

    async def test_missing_selected_input_skips_exact_generation_and_processing_children(self) -> None:
        """A missing semantic input persists precise producer and dependency-derived child guidance."""
        # Resolve a material that cannot provide the workflow's required normal texture.
        graph = (await self._prepare_graphs(self._mesh_paths[:1], self._workflow(missing_normal_input=True)))[0]

        # Submission persists the skipped producer and lets dependency propagation settle its processing child.
        self._interface.submit(graph)

        # Each row explains its own cause and neither row becomes applicable.
        graph_snapshot = self._interface.get_graph_snapshots()[0]
        generation, processing = graph_snapshot.jobs
        self.assertIs(generation.state, JobState.SKIPPED)
        self.assertEqual(generation.state_reason, "This material has no normal (OpenGL) texture.")
        self.assertIs(processing.state, JobState.SKIPPED)
        self.assertIn(f'Prerequisite "{graph.jobs[0].name}"', processing.state_reason)
        self.assertIn("This material has no normal (OpenGL) texture.", processing.state_reason)
        self.assertIs(generation.apply_disposition, ApplyDisposition.NOT_APPLICABLE)
        self.assertIs(processing.apply_disposition, ApplyDisposition.NOT_APPLICABLE)
