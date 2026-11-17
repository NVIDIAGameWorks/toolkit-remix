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

__all__ = ["TestJobQueueGraphCleanupE2E"]

import asyncio
import os
import shutil
import stat
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from carb.settings import get_settings
from lightspeed.common.constants import WindowNames
from lightspeed.trex.asset_modifiers.core import AssetModifiersCore
from lightspeed.trex.asset_modifiers.core.constants import FILE_INPUT, SETTINGS_ROOT, SOURCE_INPUT
from lightspeed.trex.asset_modifiers.core.enums import SourceGetter
from lightspeed.trex.asset_modifiers.core.settings import AssetModifierSettings
from lightspeed.trex.asset_modifiers.core.tests.e2e.scale_mesh_job import ScaleMeshTestJob
from lightspeed.trex.asset_modifiers.core.tests.e2e.scale_mesh_modifier import ScaleMeshTestModifier
from lightspeed.trex.asset_modifiers.factory import get_instance
from lightspeed.trex.asset_pipeline.core.jobs import MeshOptimizationJob
from lightspeed.trex.comfyui.core.enums import RemixType
from lightspeed.trex.comfyui.core.job import ComfyUIAssetJob, ComfyUIJob
from lightspeed.trex.comfyui.core.models import ComfyUIInputBinding, ComfyUIWorkflowRequest, Workflow
from lightspeed.trex.job_queue.widget.usage_provider import get_usage_snapshot
from omni import ui
from omni.flux.job_queue.core import get_job_queue, handlers
from omni.flux.job_queue.core.enums import EXECUTING_JOB_STATES, ApplyDisposition, JobState
from omni.flux.job_queue.core.handlers import get_apply_executor
from omni.flux.job_queue.core.job import JobGraph
from omni.flux.job_queue.core.settings import AUTO_APPLY_SETTING_PATH, SCHEDULER_ENABLED_SETTING_PATH, JobQueueSettings
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.usd import create_context, destroy_context, get_context
from pxr import Sdf, Usd, UsdGeom

_MESH = "/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"
_QUEUE_TITLE = str(WindowNames.JOB_QUEUE)
_SOURCE_MODEL = "deps/captures/meshes/mesh_0AB745B8BEE1F16B.usda"


class TestJobQueueGraphCleanupE2E(AsyncTestCase):
    """Delete real graphs without removing files that a stage or pending job needs."""

    async def test_delete_graphs_after_in_place_apply_removes_unused_output_and_keeps_stage_output(self):
        """Delete replaced outputs and graph records without removing the stage's current mesh."""
        # Apply a modifier to the selected mesh so the stage refers to its published output.
        async with self.__workflow(selected=True):
            first, modifier, old = await self.__run()
            owner = get_context("").get_stage().GetPrimAtPath(_MESH.rsplit("/", 1)[0])
            target = next(str(prim.GetPath()) for prim in Usd.PrimRange(owner) if prim.IsA(UsdGeom.Mesh))
            # Replace that mesh again so the first output becomes unused and the second remains in use.
            second, _modifier, current = await self.__run(modifier.source_url, [target])
            snapshot = await get_usage_snapshot()
            self.assertIn(os.path.normcase(os.path.realpath(current.asset_url)), snapshot.used)
            self.assertNotIn(os.path.normcase(os.path.realpath(old.asset_url)), snapshot.used)
            self.assertIs(self.__queue.usage_snapshot_provider, get_usage_snapshot)
            # Confirm deletion of both graphs and expect only the unused output folder to disappear.
            await self.__delete(first, Path(modifier.output_url))
            await self.__delete(second)
            self.assertTrue(Path(current.asset_url).is_file())
            self.assertTrue(Path(f"{current.asset_url}.meta").is_file())

    async def test_delete_producer_with_pending_modifier_keeps_source_and_consumer_runs(self):
        """Keep a deleted producer's source until its queued modifier finishes execution."""
        # Publish a source, then stop dispatch so its consumer remains queued during producer deletion.
        async with self.__workflow():
            producer, _modifier, result = await self.__run()
            JobQueueSettings().set_scheduler_enabled(False)
            status = f"{_QUEUE_TITLE}//Frame/**/Label[*].identifier=='scheduler_status'"
            await self.__wait(lambda: (label := ui_test.find(status)) and label.widget.text == "Stopped")
            # Persist a modifier input that refers to the producer's output and expect its source to survive deletion.
            AssetModifierSettings().set_value(ScaleMeshTestModifier, FILE_INPUT, Path(result.asset_url))
            _consumer, modifier, terminal = await self.__run(pending=True)
            self.assertIs(self.__queue.get_job_snapshot(modifier.job_id).state, JobState.QUEUED)
            await self.__keep(producer, result.asset_url)
            # Resume dispatch and expect the queued consumer to finish with a real mesh output.
            JobQueueSettings().set_scheduler_enabled(True)
            output = (await terminal.outputs(timeout=120))[MeshOptimizationJob.OPTIMIZED_MESH]
            self.assertTrue(Path(output.asset_url).is_file())
            self.assertIs(self.__queue.get_job_snapshot(terminal.job_id).state, JobState.DONE)

    async def test_delete_producer_with_external_comfyui_mesh_keeps_texture_dependency(self):
        """Check persisted direct inputs and external USD dependencies for both ComfyUI job types."""
        for external in (False, True):
            with self.subTest(external=external), TemporaryDirectory() as directory:
                # Publish an output and optionally refer to its texture from a mesh outside the project.
                async with self.__workflow() as project:
                    producer, modifier, result = await self.__run()
                    source, protected = result.asset_url, result.asset_url
                    if external:
                        protected = str(Path(modifier.output_url) / "dependency.dds")
                        shutil.copyfile(project / "sources/textures/ingested/16px_Diffuse.dds", protected)
                        source = str(Path(directory) / "external.usda")
                        stage = Usd.Stage.CreateNew(source)
                        prim = UsdGeom.Mesh.Define(stage, "/Mesh").GetPrim()
                        prim.CreateAttribute("texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(protected))
                        stage.Save()
                        stage = None
                        self.assertFalse(Path(source).is_relative_to(project))
                    # Queue both ComfyUI job types and expect their saved inputs to retain the source path.
                    JobQueueSettings().set_scheduler_enabled(False)
                    binding = ComfyUIInputBinding("1.inputs.mesh_file_path", RemixType.MESH_FILE_PATH, source)
                    prompt = {"1": {"class_type": "RTXRemixImportMeshNode", "inputs": {"mesh_file_path": source}}}
                    request = ComfyUIWorkflowRequest(
                        prompt, (binding,), "graph-cleanup", 0.0, None, Workflow(name="Cleanup")
                    )
                    consumers = JobGraph(name="Pending ComfyUI inputs", jobs=[ComfyUIJob(), ComfyUIAssetJob()])
                    for job in consumers.jobs:
                        consumers.bind(job, job.WORKFLOW_REQUEST, request)
                    for handle in self.__record(consumers):
                        self.assertIs(self.__queue.get_job_snapshot(handle.job_id).state, JobState.QUEUED)
                        saved = self.__queue.resolve_job_inputs(handle.job_id)[ComfyUIJob.WORKFLOW_REQUEST]
                        self.assertEqual(saved.input_bindings[0].source, source)
                    # Delete the producer graph and expect its direct or transitive input file to remain.
                    await self.__keep(producer, protected, metadata=not external)

    async def test_delete_graph_keeps_closed_references_and_failed_project_scan(self):
        """Remove graph records but keep outputs after a closed reference or an unrelated project scan failure."""
        for invalid_scan in (False, True):
            with self.subTest(invalid_scan=invalid_scan), TemporaryDirectory() as directory:
                # Publish an output and prepare either a closed referrer or an independent project root.
                async with self.__workflow() as project:
                    graph, modifier, result = await self.__run()
                    referrer = (
                        Path(directory) / "other_project.usda"
                        if invalid_scan
                        else Path(modifier.output_url).parent / "closed_reference.usda"
                    )
                    stage = Usd.Stage.CreateNew(str(referrer))
                    if not invalid_scan:
                        stage.DefinePrim("/Keep").GetReferences().AddReference(result.asset_url)
                    stage.Save()
                    stage = None
                    context_name = f"graph-cleanup-{uuid.uuid4()}"
                    context = create_context(context_name) if invalid_scan else None
                    invalid = referrer.parent / "invalid.usda"
                    try:
                        if context:
                            # Verify both independent roots before an invalid file makes the other project unreadable.
                            await context.open_stage_async(str(referrer))
                            snapshot = await get_usage_snapshot()
                            self.assertIn(os.path.normcase(os.path.realpath(project)), snapshot.verified_roots)
                            self.assertIn(os.path.normcase(os.path.realpath(referrer.parent)), snapshot.verified_roots)
                            self.assertFalse(referrer.parent.is_relative_to(project))
                            self.assertFalse(project.is_relative_to(referrer.parent))
                            invalid.write_text(
                                f'#usda 1.0\ndef Xform "Unclosed" (references = @{result.asset_url}@) {{',
                                encoding="utf-8",
                            )
                            self.assertEqual((await get_usage_snapshot()).verified_roots, frozenset())
                        # Remove the graph and expect the closed reference or failed scan to preserve the output.
                        await self.__keep(graph, result.asset_url, invalid_scan=invalid_scan)
                    finally:
                        # Close the extra project and remove its invalid file before the workflow restores the queue.
                        invalid.unlink(missing_ok=True)
                        if context:
                            await context.close_stage_async()
                            destroy_context(context_name)

    async def __keep(self, graph, path, *, invalid_scan=False, metadata=True):
        snapshot = await get_usage_snapshot()
        root = os.path.normcase(os.path.realpath(self.__project))
        self.assertEqual(root in snapshot.verified_roots, not invalid_scan)
        self.assertNotIn(os.path.normcase(os.path.realpath(path)), snapshot.used)
        await asyncio.to_thread(self.__queue.delete_graphs, [graph.graph_id], snapshot)
        self.assertNotIn(graph.graph_id, {item.graph_id for item in self.__queue.get_graph_snapshots()})
        self.assertTrue(Path(path).is_file())
        if metadata:
            self.assertTrue(Path(f"{path}.meta").is_file())

    @asynccontextmanager
    async def __workflow(self, *, selected=False):
        settings = get_settings()
        keys = [AUTO_APPLY_SETTING_PATH, SCHEDULER_ENABLED_SETTING_PATH, f"{SETTINGS_ROOT}/active_modifier"]
        keys.extend(
            AssetModifierSettings.get_value_key(ScaleMeshTestModifier, item) for item in (SOURCE_INPUT, FILE_INPUT)
        )
        original = {key: settings.get(key) for key in keys}
        window = ui.Workspace.get_window(_QUEUE_TITLE)
        geometry = (window.position_x, window.position_y, window.width, window.height, bool(window.visible))
        self.__queue, self.__graphs = get_job_queue(), {}
        modifier_settings = AssetModifierSettings()
        get_instance().register_plugins([ScaleMeshTestModifier])
        try:
            ui.Workspace.show_window(_QUEUE_TITLE, True)
            window.position_x, window.position_y, window.width, window.height = 0, 0, 1200, 600
            modifier_settings.set_active_modifier_name(ScaleMeshTestModifier.name)
            source = SourceGetter.SELECTED if selected else SourceGetter.CONSTANT
            modifier_settings.set_value(ScaleMeshTestModifier, SOURCE_INPUT, source)
            JobQueueSettings().set_auto_apply(False)
            JobQueueSettings().set_scheduler_enabled(True)
            async with open_test_project(
                "usd/project_example/combined.usda", ext_name="lightspeed.trex.app.resources"
            ) as project:
                self.__project = Path(project.path).parent
                modifier_settings.set_value(ScaleMeshTestModifier, FILE_INPUT, self.__project / _SOURCE_MODEL)
                try:
                    yield self.__project
                finally:
                    JobQueueSettings().set_scheduler_enabled(False)
                    scheduler = handlers._scheduler
                    scheduler.pause()
                    owned = [graph for graph in self.__queue.get_graph_snapshots() if graph.graph_id in self.__graphs]
                    for job in (job for graph in owned for job in graph.jobs):
                        if job.state in EXECUTING_JOB_STATES:
                            self.__queue.cancel_job(job.job_id)
                    async with asyncio.timeout(30):
                        await scheduler.stop()
                        await get_apply_executor().wait_idle()
                    if remaining := [graph.graph_id for graph in owned]:
                        await asyncio.to_thread(self.__queue.delete_graphs, remaining, await get_usage_snapshot())
                    jobs = Path(self.__queue.db_path).parent / "jobs"
                    for graph_id, graph in self.__graphs.items():
                        for directory in [
                            jobs / ".trash" / str(graph_id),
                            *(jobs / str(job.job_id) for job in graph.jobs),
                        ]:
                            if directory.exists():
                                shutil.rmtree(directory, onexc=self.__remove_readonly)
        finally:
            get_instance().unregister_plugins([ScaleMeshTestModifier])
            for key, value in original.items():
                settings.destroy_item(key) if value is None else settings.set(key, value)
            window.position_x, window.position_y, window.width, window.height, window.visible = geometry
            await ui_test.human_delay()

    @staticmethod
    def __remove_readonly(function, path, error):
        if (
            not isinstance(error, PermissionError)
            or not os.stat(path).st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
        ):
            raise error
        os.chmod(path, stat.S_IWRITE)
        function(path)

    def __record(self, graph):
        self.__graphs[graph.graph_id] = graph
        return self.__queue.submit(graph)

    async def __run(self, source_url=None, prim_paths=None, *, pending=False):
        (graph,), skipped = await AssetModifiersCore("").prepare_submission(prim_paths or [_MESH])
        self.assertEqual(skipped, {})
        modifier = next(job for job in graph.jobs if isinstance(job, ScaleMeshTestJob))
        if source_url is not None:
            modifier.source_url = source_url
        mesh = next(job for job in graph.jobs if isinstance(job, MeshOptimizationJob))
        terminal = next(handle for handle in self.__record(graph) if handle.job_id == mesh.job_id)
        if pending:
            return graph, modifier, terminal
        result = (await terminal.outputs(timeout=120))[MeshOptimizationJob.OPTIMIZED_MESH]
        await get_apply_executor().apply(terminal.job_id)
        await get_apply_executor().wait_idle()
        snapshot = self.__queue.get_job_snapshot(terminal.job_id)
        self.assertIs(snapshot.apply_disposition, ApplyDisposition.APPLIED, snapshot.apply_error)
        return graph, modifier, result

    async def __wait(self, condition):
        async with asyncio.timeout(10):
            while not condition():
                await ui_test.human_delay()

    async def __delete(self, graph, unused=None):
        directories = [
            self.__queue.get_job_directory(job.job_id)
            for job in graph.jobs
            if self.__queue.get_job_snapshot(job.job_id).apply_disposition is not ApplyDisposition.APPLIED
        ]
        if unused:
            directories.append(unused)
        count = sum(len(files) for directory in directories for _root, _children, files in os.walk(directory))
        button = f"{_QUEUE_TITLE}//Frame/**/Image[*].identifier=='delete_graph_{graph.graph_id}'"
        await self.__wait(lambda: (item := ui_test.find(button)) and item.widget.enabled and item.size.x > 0)
        await ui_test.human_delay()
        await ui_test.find(button).click()
        title = "Delete Job Graph"
        await self.__wait(
            lambda: any(window.title == title and window.visible for window in ui.Workspace.get_windows())
        )
        self.assertTrue(
            any(
                f"and {count} output file" in label.widget.text
                for label in ui_test.find_all(f"{title}//Frame/**/Label[*]")
            )
        )
        await ui_test.find(f"{title}//Frame/**/Button[*].name=='confirm_button'").click()
        await self.__wait(lambda: graph.graph_id not in {item.graph_id for item in self.__queue.get_graph_snapshots()})
        await self.__wait(lambda: not any(directory.exists() for directory in directories) and not ui_test.find(button))
