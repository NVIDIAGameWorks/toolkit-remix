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

import json
import pathlib
import shutil
import tempfile
import uuid
from unittest import mock

import omni.client
import omni.kit.app
import omni.kit.test
import omni.usd
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core import handlers
from omni.flux.job_queue.core.apply_executor import ApplyExecutor
from omni.flux.job_queue.core.enums import ApplyDisposition, JobState
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.job import (
    Job,
    JobGraph,
    JobInputPort,
    JobInputs,
    JobOutputPort,
    JobOutputs,
    JobProgress,
    JobProgressCallback,
)
from omni.flux.job_queue.core.execute import JobScheduler
from omni.flux.job_queue.core.persistence import PersistenceCodec, get_registry
from omni.flux.utils.common.path_utils import hash_file, read_metadata
from omni.flux.utils.tests.context_managers import open_test_project
from pxr import Sdf, Usd, UsdGeom, UsdShade, UsdUtils

import lightspeed.trex.asset_pipeline.core.utils as utils_module
from lightspeed.trex.asset_pipeline.core.constants import PROCESSED_OUTPUT_DIR_NAME
from lightspeed.trex.asset_pipeline.core.extension import AssetPipelineCoreExtension
from lightspeed.trex.asset_pipeline.core.jobs import (
    MeshOptimizationJob,
    PrepareOptimizationJob,
    TextureProcessingJob,
    build_asset_optimization_graph,
)
from lightspeed.trex.asset_pipeline.core.metadata import (
    get_current_validation_extensions,
)
from lightspeed.trex.asset_pipeline.core.constants import (
    BASE_HASH_KEY,
    VALIDATION_EXTENSIONS_KEY,
    VALIDATION_PASSED_KEY,
)
from lightspeed.trex.asset_pipeline.core.jobs.models import (
    MeshOptimizationRequest,
    MeshOptimizationResult,
    PrepareOptimizationResult,
    TextureProcessingItem,
    TextureProcessingRequest,
    TextureProcessingResult,
)
from lightspeed.trex.asset_pipeline.core.pipeline.item import AssetKind
from lightspeed.trex.asset_pipeline.core.steps import ConvertDDSStep, ConvertNormalStep


def _json_round_trip(value):
    """Return ``value`` after one JSON encode/decode pass.

    A metadata sidecar is JSON, so a tuple written through it reads back as a list. Comparing
    live in-memory data (which may carry tuples, e.g. an extension's ``version``) against a value
    read from a sidecar must normalize through the same encode/decode pass first.

    Args:
        value: JSON-serializable data to normalize.

    Returns:
        The value after round-tripping through ``json.dumps``/``json.loads``.
    """
    return json.loads(json.dumps(value))


class _RequestProducer(Job):
    """Return a bound texture request through a real typed graph connection."""

    REQUEST = JobInputPort("request", TextureProcessingRequest)
    RESULT = JobOutputPort("result", TextureProcessingRequest)
    input_ports = (REQUEST,)
    output_ports = (RESULT,)

    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Forward the bound request through the scheduler.

        Args:
            job_directory: Queue-owned directory unused by this in-memory producer.
            inputs: Typed request input.
            progress_callback: Async callback receiving producer progress.

        Returns:
            The exact request supplied through the input port.
        """
        del job_directory
        await progress_callback(JobProgress(completed=1, total=1, detail="Prepare textures"))
        return JobOutputs({self.RESULT: inputs[self.REQUEST]})


def _encode_request_producer(job: _RequestProducer) -> tuple:
    """Encode the real E2E producer without introspection.

    Args:
        job: Producer job to persist.

    Returns:
        Canonical base-job payload.
    """
    return job.job_id, job.name, job.skip_reason, job.apply_binding


def _decode_request_producer(payload: tuple) -> _RequestProducer:
    """Decode the real E2E producer from its canonical payload.

    Args:
        payload: Canonical base-job payload.

    Returns:
        Reconstructed producer job.
    """
    job_id, name, skip_reason, apply_binding = payload
    return _RequestProducer(
        job_id=job_id,
        name=name,
        skip_reason=skip_reason,
        apply_binding=apply_binding,
    )


_REQUEST_PRODUCER_CODEC = PersistenceCodec(
    "test.asset_pipeline.RequestProducer",
    _RequestProducer,
    _encode_request_producer,
    _decode_request_producer,
)


class TestTextureProcessingJobE2E(omni.kit.test.AsyncTestCase):
    """Exercise the reusable texture job through real queue and client boundaries."""

    async def setUp(self) -> None:
        """Register the test-only producer job."""
        get_registry().register_codecs([_REQUEST_PRODUCER_CODEC])

    async def tearDown(self) -> None:
        """Unregister the test-only producer job."""
        get_registry().unregister_codecs([_REQUEST_PRODUCER_CODEC])

    async def test_literal_request_persists_real_outputs_and_per_asset_progress(self):
        """A literal request reports completed textures and monotonic per-texture progress."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_fixture = _get_normal_fixture_path()
            source_paths = (temp_path / "normal_a.png", temp_path / "normal_b.png")
            for source_path in source_paths:
                shutil.copy2(source_fixture, source_path)
            request = _make_texture_request(source_paths, temp_path / "processed")
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Literal texture optimization")
            job = TextureProcessingJob(name="Process two textures")
            graph.add_job(job)
            graph.bind(job, TextureProcessingJob.SOURCE_TEXTURES, request)
            queue_job = interface.submit(graph)[0]
            progress: list[JobProgress] = []

            def record_progress(changed_job_id, current_progress: JobProgress) -> None:
                """Record committed progress for the submitted job.

                Args:
                    changed_job_id: Identifier whose queue state changed.
                    current_progress: Exact progress value committed for the job.
                """
                if changed_job_id == job.job_id:
                    progress.append(current_progress)

            subscription = interface.subscribe_job_progress_changed(record_progress)

            # Let the real scheduler process both bound textures while queue notifications capture durable progress.
            outputs = await _run_until_outputs(queue_job, interface)

            del subscription

            # The typed result contains both textures and progress advances monotonically to the complete batch.
            result = outputs[TextureProcessingJob.PROCESSED_TEXTURES]
            self.assertEqual(len(result.items), 2)
            self.assertTrue(result.validation_passed)
            self.assertTrue(all(pathlib.Path(item.asset_url).is_file() for item in result.items))
            self.assertTrue(all(pathlib.Path(item.asset_url).suffix == ".dds" for item in result.items))
            completed_counts = [value.completed for value in progress]
            self.assertIn(1, completed_counts)
            self.assertEqual(completed_counts[-1], 2)
            self.assertTrue(all(value.total == 2 for value in progress))
            self.assertEqual(completed_counts, sorted(completed_counts))

    async def test_request_without_destination_publishes_to_durable_job_directory(self):
        """Project-independent processing keeps real outputs with the persisted queue job."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "normal.png"
            shutil.copy2(_get_normal_fixture_path(), source_path)
            request = TextureProcessingRequest(
                items=(
                    TextureProcessingItem(
                        key="normal",
                        path=source_path,
                        texture_type=TextureTypes.NORMAL_DX,
                    ),
                ),
                source_root=temp_path,
                output_url=None,
            )
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Project-independent texture optimization")
            job = TextureProcessingJob(name="Optimize one texture")
            graph.add_job(job)
            graph.bind(job, TextureProcessingJob.SOURCE_TEXTURES, request)
            queue_job = interface.submit(graph)[0]

            # Run the real scheduler and pipeline without a project-owned publication URL.
            outputs = await _run_until_outputs(queue_job, interface)

            # The durable result stays below the queue-owned job directory and survives output reconstruction.
            output = pathlib.Path(outputs[TextureProcessingJob.PROCESSED_TEXTURES].items[0].asset_url)
            self.assertTrue(output.is_file())
            self.assertEqual(output.parent, interface.get_job_directory(job.job_id) / PROCESSED_OUTPUT_DIR_NAME)
            self.assertEqual(
                interface.get_job_outputs(job.job_id)[TextureProcessingJob.PROCESSED_TEXTURES],
                outputs[TextureProcessingJob.PROCESSED_TEXTURES],
            )

    async def test_completed_outputs_reconstruct_through_fresh_queue_interface(self):
        """A fresh queue interface reconstructs a completed typed texture result."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            request = _make_texture_request((_get_normal_fixture_path(),), temp_path / "processed")
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Durable texture optimization")
            job = TextureProcessingJob(name="Process durable texture")
            graph.add_job(job)
            graph.bind(job, TextureProcessingJob.SOURCE_TEXTURES, request)
            queue_job = interface.submit(graph)[0]

            # Complete the texture job, then reopen its SQLite database through a fresh queue interface.
            outputs = await _run_until_outputs(queue_job, interface)

            restored_outputs = _reopen_outputs(queue_job, interface)

            # Typed outputs survive serialization and reconstruct without relying on the original interface.
            self.assertEqual(restored_outputs, outputs)

    async def test_independent_jobs_preserve_source_hierarchy_in_shared_output_directory(self):
        """Independent jobs keep same-named source textures at distinct stable destinations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_root = temp_path / "project"
            table_source = source_root / "textures" / "table" / "albedo.png"
            chair_source = source_root / "textures" / "chair" / "albedo.png"
            for source_path in (table_source, chair_source):
                source_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(_get_normal_fixture_path(), source_path)
            output_dir = temp_path / "ProcessedTextures"
            interface = QueueInterface(str(temp_path / "queue.sqlite"))

            # Submit and complete separate graphs so each job owns an independent pipeline context.
            results = []
            for name, source_path in (("Table", table_source), ("Chair", chair_source)):
                graph = JobGraph(name=name)
                job = TextureProcessingJob(name=f"Process {name}")
                graph.add_job(job)
                graph.bind(
                    job,
                    TextureProcessingJob.SOURCE_TEXTURES,
                    _make_texture_request((source_path,), output_dir, source_root=source_root),
                )
                results.append(
                    (await _run_until_outputs(interface.submit(graph)[0], interface))[job.PROCESSED_TEXTURES]
                )

            # Source-relative folders and processing semantics make both durable results collision-free.
            table_output = pathlib.Path(results[0].items[0].asset_url)
            chair_output = pathlib.Path(results[1].items[0].asset_url)
            expected_name = "albedo_OTH_Normal.n.rtex.dds"
            self.assertEqual(table_output.relative_to(output_dir), pathlib.Path("textures/table") / expected_name)
            self.assertEqual(chair_output.relative_to(output_dir), pathlib.Path("textures/chair") / expected_name)
            self.assertTrue(table_output.exists())
            self.assertTrue(chair_output.exists())

    async def test_extension_shutdown_keeps_codecs_until_active_queue_work_drains(self):
        """Texture jobs serialize successful outputs after their product extension begins shutdown."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            request = _make_texture_request((_get_normal_fixture_path(),), temp_path / "processed")
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Drain texture optimization")
            job = TextureProcessingJob(name="Finish active processing")
            graph.add_job(job)
            graph.bind(job, TextureProcessingJob.SOURCE_TEXTURES, request)
            queue_job = interface.submit(graph)[0]

            # Product shutdown runs before the core queue drains work during application shutdown.
            AssetPipelineCoreExtension().on_shutdown()
            outputs = await _run_until_outputs(queue_job, interface)

            # The active job completes and persists its typed output before core-owned registry teardown.
            self.assertIs(queue_job.snapshot().state, JobState.DONE)
            self.assertEqual(len(outputs[TextureProcessingJob.PROCESSED_TEXTURES].items), 1)

    async def test_connected_request_reaches_texture_job_through_real_scheduler(self):
        """A producer output supplies the exact connected texture-processing input."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            request = _make_texture_request((_get_normal_fixture_path(),), temp_path / "processed")
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Connected texture optimization")
            producer = _RequestProducer(name="Prepare request")
            processor = TextureProcessingJob(name="Process request")
            graph.add_job(producer)
            graph.add_job(processor)
            graph.bind(producer, _RequestProducer.REQUEST, request)
            graph.connect(
                producer.output(_RequestProducer.RESULT),
                processor.input(TextureProcessingJob.SOURCE_TEXTURES),
            )
            producer_queue_job, processor_queue_job = interface.submit(graph)

            # Run the connected graph so the scheduler forwards the producer's output into texture optimization.
            outputs = await _run_until_outputs(processor_queue_job, interface)

            # Both stages settle and the processor publishes the texture represented by the connected request.
            self.assertIs(producer_queue_job.snapshot().state, JobState.DONE)
            result = outputs[TextureProcessingJob.PROCESSED_TEXTURES]
            self.assertEqual(len(result.items), 1)
            self.assertEqual(result.items[0].key, "texture_1")

    async def test_queue_publication_failure_persists_failed_state_without_apply_ready_output(self):
        """A publication failure crosses the real queue boundary without durable outputs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            request = _make_texture_request(
                (_get_normal_fixture_path(),),
                "omniverse://server/project/processed",
            )
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Failed texture publication")
            job = TextureProcessingJob(name="Publish processed texture")
            graph.add_job(job)
            graph.bind(job, TextureProcessingJob.SOURCE_TEXTURES, request)
            queue_job = interface.submit(graph)[0]

            # Fail at the real publication boundary after the queue has claimed and executed the job.
            with (
                mock.patch.object(
                    utils_module,
                    "_publish_remote_batch",
                    new=mock.AsyncMock(side_effect=RuntimeError("injected publication failure")),
                ),
                self.assertRaisesRegex(RuntimeError, "injected publication failure"),
            ):
                await _run_until_outputs(queue_job, interface)

            # Queue failure is durable, not Apply-ready, and cannot expose a partial typed result.
            snapshot = queue_job.snapshot()
            self.assertIs(snapshot.state, JobState.FAILED)
            self.assertIs(snapshot.apply_disposition, ApplyDisposition.NOT_APPLICABLE)
            with self.assertRaises(KeyError):
                interface.get_job_outputs(job.job_id)


class TestMeshOptimizationGraphE2E(omni.kit.test.AsyncTestCase):
    """Exercise the connected prepare, texture, and mesh optimization graph through the real queue."""

    async def test_prepare_with_udim_tiles_returns_texture_request(self):
        """Preparation returns the UDIM pattern and preserves both source tiles for the texture job."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_dir = temp_path / "source"
            texture_dir = source_dir / "textures"
            texture_dir.mkdir(parents=True)
            tile_names = ("tile.1001.png", "tile.1002.png")
            source_fixture = _get_normal_fixture_path()
            for tile_name in tile_names:
                shutil.copy2(source_fixture, texture_dir / tile_name)
            source_model = source_dir / "model.usda"
            source_model.write_text(_make_model_usda(pathlib.Path("textures/tile.<UDIM>.png")), encoding="utf-8")

            outputs = await PrepareOptimizationJob().execute(
                temp_path / "prepare",
                JobInputs(
                    {
                        PrepareOptimizationJob.SOURCE_MODEL: MeshOptimizationRequest(
                            source_path=source_model, source_root=source_dir
                        )
                    }
                ),
                mock.AsyncMock(),
            )

            texture_request = outputs[PrepareOptimizationJob.TEXTURE_REQUEST]
            self.assertEqual(
                [(item.path.name, item.texture_type) for item in texture_request.items],
                [("tile.<UDIM>.png", TextureTypes.DIFFUSE)],
            )
            for tile_name in tile_names:
                self.assertEqual(
                    texture_request.items[0].path.with_name(tile_name).read_bytes(), source_fixture.read_bytes()
                )
            self.assertTrue(outputs[PrepareOptimizationJob.PREPARED_MESH].model_work_path.is_file())

    async def test_prepare_preserves_destination_and_keeps_intermediate_textures_local(self):
        """Preparation preserves the final destination without publishing intermediate textures there."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_model = _get_textured_fbx_fixture_path()
            output_url = "omniverse://server/project/assets/ingested/comfyui/job"
            outputs = await PrepareOptimizationJob().execute(
                pathlib.Path(temp_dir) / "prepare",
                JobInputs(
                    {
                        PrepareOptimizationJob.SOURCE_MODEL: MeshOptimizationRequest(
                            source_path=source_model,
                            source_root=source_model.parent,
                            output_url=output_url,
                        )
                    }
                ),
                mock.AsyncMock(),
            )
            prepared = outputs[PrepareOptimizationJob.PREPARED_MESH]
            texture_request = outputs[PrepareOptimizationJob.TEXTURE_REQUEST]
            self.assertEqual(prepared.output_url, output_url)
            self.assertIsNone(texture_request.output_url)
            self.assertEqual(texture_request.items, prepared.texture_items)
            self.assertTrue(prepared.model_work_path.is_file())

    async def test_connected_graph_converts_omni_glass_textures_to_final_dds(self):
        """Convert every OmniGlass texture before the mesh job renames its shader inputs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            textures_dir = temp_path / "textures"
            textures_dir.mkdir()
            source_textures = {
                "inputs:glass_color_texture": textures_dir / "glass_color.png",
                "inputs:roughness_texture": textures_dir / "glass_rough.png",
                "inputs:normal_map_texture": textures_dir / "glass_normal.png",
            }
            for texture_path in source_textures.values():
                shutil.copy2(_get_normal_fixture_path(), texture_path)

            # An OmniGlass shader names each texture under its own input, which only the material
            # conversion in the later mesh phase renames to the Aperture input.
            glass_inputs = "\n".join(
                f"            asset {input_name} = @{texture_path.as_posix()}@"
                for input_name, texture_path in source_textures.items()
            )
            source_model = temp_path / "model.usda"
            source_model.write_text(
                _make_model_usda(source_textures["inputs:glass_color_texture"])
                .replace("OmniPBR", "OmniGlass")
                .replace(
                    f"            asset inputs:diffuse_texture = "
                    f"@{source_textures['inputs:glass_color_texture'].as_posix()}@",
                    glass_inputs,
                ),
                encoding="utf-8",
            )

            # Run the complete graph so discovery precedes material conversion.
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph, mesh_job = build_asset_optimization_graph(
                MeshOptimizationRequest(source_path=source_model, source_root=temp_path)
            )
            queue_jobs = {queue_job.job_id: queue_job for queue_job in interface.submit(graph)}
            result = (await _run_until_outputs(queue_jobs[mesh_job.job_id], interface))[
                MeshOptimizationJob.OPTIMIZED_MESH
            ]

            # Every published Aperture input binds a converted texture beside the model, never a PNG.
            final_model = pathlib.Path(result.asset_url)
            stage = Usd.Stage.Open(str(final_model))
            shaders = [prim for prim in stage.Traverse() if prim.IsA(UsdShade.Shader)]
            self.assertEqual(len(shaders), 1)
            for aperture_input in (
                "inputs:diffuse_texture",
                "inputs:reflectionroughness_texture",
                "inputs:normalmap_texture",
            ):
                attribute = shaders[0].GetAttribute(aperture_input)
                self.assertTrue(attribute, aperture_input)
                texture = attribute.Get()
                self.assertTrue(texture.path.endswith(".rtex.dds"), f"{aperture_input}: {texture.path}")
                texture_path = (final_model.parent / texture.path).resolve()
                self.assertEqual(texture_path.parent, (final_model.parent / "textures").resolve())
                self.assertTrue(texture_path.is_file(), texture.path)

    async def test_connected_graph_keeps_same_named_textures_from_two_folders_apart(self):
        """Same-named textures in two folders keep distinct stable outputs across repeated runs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_root = temp_path / "project"
            for folder in ("a", "b"):
                (source_root / folder).mkdir(parents=True)
                shutil.copy2(_get_normal_fixture_path(), source_root / folder / "albedo.png")

            # One shader per folder, both naming a file called albedo.png.
            source_model = source_root / "model.usda"
            source_model.write_text(
                _make_model_usda(source_root / "a" / "albedo.png").replace(
                    '    def Material "Material"',
                    f"""
    def Material "SecondMaterial"
    {{
        token outputs:mdl:surface.connect = </Quad/SecondMaterial/Shader.outputs:out>

        def Shader "Shader"
        {{
            uniform token info:implementationSource = "sourceAsset"
            uniform asset info:mdl:sourceAsset = @OmniPBR.mdl@
            uniform token info:mdl:sourceAsset:subIdentifier = "OmniPBR"
            asset inputs:diffuse_texture = @{(source_root / "b" / "albedo.png").as_posix()}@ (
                colorSpace = "auto"
            )
            token outputs:out (
                renderType = "material"
            )
        }}
    }}
    def Material "Material"
""",
                    1,
                ),
                encoding="utf-8",
            )
            stage = Usd.Stage.Open(str(source_model))
            layer = stage.GetRootLayer()
            Sdf.CopySpec(layer, "/Quad/Quad", layer, "/Quad/Quad2")
            stage.GetPrimAtPath("/Quad/Quad2").GetRelationship("material:binding").SetTargets(["/Quad/SecondMaterial"])
            layer.Save()
            del stage, layer

            destination = temp_path / "published"

            async def publish_once() -> set[str]:
                """Run the complete graph into one destination and return its published DDS paths."""
                interface = QueueInterface(str(temp_path / f"queue_{uuid.uuid4().hex}.sqlite"))
                graph, mesh_job = build_asset_optimization_graph(
                    MeshOptimizationRequest(
                        source_path=source_model,
                        source_root=source_root,
                        output_url=omni.client.make_file_url(str(destination)),
                    )
                )
                queue_jobs = {queue_job.job_id: queue_job for queue_job in interface.submit(graph)}
                await _run_until_outputs(queue_jobs[mesh_job.job_id], interface)
                return {path.relative_to(destination).as_posix() for path in destination.rglob("*.dds")}

            first_paths = await publish_once()
            # Each source keeps its own folder under the destination; neither carries a workspace name.
            self.assertEqual(first_paths, {"a/albedo.a.rtex.dds", "b/albedo.a.rtex.dds"})

            # A second run into the same destination lands on the same paths and adds no stray file.
            self.assertEqual(await publish_once(), first_paths)

    async def test_connected_graph_processes_real_model_to_final_dds_references(self):
        """Prepare, texture, and mesh jobs run in dependency order in one connected graph."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_model = _get_textured_fbx_fixture_path()
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Texture-first model processing")
            prepare_job = PrepareOptimizationJob(name="Prepare optimization")
            texture_job = TextureProcessingJob(name="Optimize textures")
            mesh_job = MeshOptimizationJob(name="Optimize mesh")
            graph.add_job(prepare_job)
            graph.add_job(texture_job)
            graph.add_job(mesh_job)
            graph.bind(
                prepare_job,
                PrepareOptimizationJob.SOURCE_MODEL,
                MeshOptimizationRequest(
                    source_path=source_model,
                    source_root=source_model.parent,
                ),
            )
            graph.connect(
                prepare_job.output(PrepareOptimizationJob.TEXTURE_REQUEST),
                texture_job.input(TextureProcessingJob.SOURCE_TEXTURES),
            )
            graph.connect(
                prepare_job.output(PrepareOptimizationJob.PREPARED_MESH),
                mesh_job.input(MeshOptimizationJob.SOURCE_MODEL),
            )
            graph.connect(
                texture_job.output(TextureProcessingJob.PROCESSED_TEXTURES),
                mesh_job.input(MeshOptimizationJob.TEXTURE_INPUT),
            )

            # The graph carries the three exact job types and their three typed dependencies.
            self.assertEqual(
                [type(job) for job in graph.jobs],
                [PrepareOptimizationJob, TextureProcessingJob, MeshOptimizationJob],
            )
            self.assertEqual(
                {(connection.source_job_id, connection.target_job_id) for connection in graph.connections},
                {
                    (prepare_job.job_id, texture_job.job_id),
                    (prepare_job.job_id, mesh_job.job_id),
                    (texture_job.job_id, mesh_job.job_id),
                },
            )

            queue_jobs = {queue_job.job_id: queue_job for queue_job in interface.submit(graph)}

            convert_normal_run = ConvertNormalStep.run
            convert_dds_run = ConvertDDSStep.run
            normal_run_kinds: list[list[AssetKind]] = []
            dds_run_kinds: list[list[AssetKind]] = []

            async def record_normal_run(step, context):
                """Record the item kinds reaching normal conversion, then forward the call.

                Args:
                    step: Conversion step instance being run.
                    context: Pipeline context carrying the current batch.
                """
                normal_run_kinds.append([item.kind for item in context.items])
                await convert_normal_run(step, context)

            async def record_dds_run(step, context):
                """Record the item kinds reaching DDS conversion, then forward the call.

                Args:
                    step: Conversion step instance being run.
                    context: Pipeline context carrying the current batch.
                """
                dds_run_kinds.append([item.kind for item in context.items])
                await convert_dds_run(step, context)

            # Run the real scheduler through prepare, texture processing, and mesh optimization.
            with (
                mock.patch.object(ConvertNormalStep, "run", record_normal_run),
                mock.patch.object(ConvertDDSStep, "run", record_dds_run),
            ):
                outputs = await _run_until_outputs(queue_jobs[mesh_job.job_id], interface)

            # Texture conversion only ever ran inside the texture job, never on the model item.
            self.assertFalse(any(AssetKind.MODEL in kinds for kinds in normal_run_kinds))
            self.assertTrue(dds_run_kinds)
            self.assertTrue(all(kinds == [AssetKind.TEXTURE] for kinds in dds_run_kinds))

            # All three jobs settle in order and the final model is published.
            self.assertIs(queue_jobs[prepare_job.job_id].snapshot().state, JobState.DONE)
            self.assertIs(queue_jobs[texture_job.job_id].snapshot().state, JobState.DONE)
            self.assertIs(queue_jobs[mesh_job.job_id].snapshot().state, JobState.DONE)
            result = outputs[MeshOptimizationJob.OPTIMIZED_MESH]
            self.assertIsInstance(result, MeshOptimizationResult)
            self.assertEqual(result.source_path, source_model)
            self.assertTrue(result.validation_passed)
            final_model = pathlib.Path(result.asset_url)
            self.assertTrue(final_model.is_file())
            self.assertEqual(final_model.suffix, ".usd")

            # The model lineage entry hashes the original FBX source, not the published USD output.
            model_entry = result.lineage[0]
            self.assertEqual(model_entry[0], str(source_model))
            self.assertEqual(model_entry[2], hash_file(str(source_model)))
            self.assertNotEqual(model_entry[2], hash_file(str(final_model)))

            # The prepare job discovered the model's textures and layers without mutating the stage.
            prepare_outputs = interface.get_job_outputs(prepare_job.job_id)
            prepared = prepare_outputs[PrepareOptimizationJob.PREPARED_MESH]
            self.assertTrue(prepared.texture_items)
            self.assertTrue(prepared.referenced_layers)
            self.assertEqual(prepared.source_path, source_model)
            self.assertEqual(prepared.source_root, source_model.parent)
            self.assertIsNone(prepared.output_url)
            texture_request = prepare_outputs[PrepareOptimizationJob.TEXTURE_REQUEST]
            self.assertEqual(texture_request.items, prepared.texture_items)
            self.assertEqual(texture_request.source_root, source_model.parent)
            self.assertIsNone(texture_request.output_url)
            self.assertEqual(_reopen_outputs(queue_jobs[prepare_job.job_id], interface), prepare_outputs)

            # The texture job published exactly the collected texture batch, correlated by stable keys.
            processed = interface.get_job_outputs(texture_job.job_id)[TextureProcessingJob.PROCESSED_TEXTURES]
            self.assertEqual(
                {item.key for item in processed.items},
                {item.key for item in prepared.texture_items},
            )
            published_dds = [pathlib.Path(item.asset_url) for item in processed.items]
            self.assertTrue(all(path.is_file() for path in published_dds))
            self.assertTrue(processed.validation_passed)

            # The mesh result carries the same textures re-based onto the copies published beside the
            # model, at the legacy ``textures/<name>`` layout, with keys, semantics, and hashes intact.
            self.assertEqual(
                [(item.key, item.texture_type) for item in result.texture_result.items],
                [(item.key, item.texture_type) for item in processed.items],
            )
            for item in result.texture_result.items:
                published = pathlib.Path(item.asset_url)
                self.assertEqual(published.parent, final_model.parent / "textures")
                self.assertTrue(published.is_file())
            self.assertEqual(
                [(entry[0], entry[2]) for entry in result.texture_result.lineage],
                [(entry[0], entry[2]) for entry in processed.lineage],
            )
            self.assertEqual(
                [entry[1] for entry in result.texture_result.lineage],
                [item.asset_url for item in result.texture_result.items],
            )

            # The texture job's published batch also reconstructs through a fresh queue interface,
            # proving the connected graph's texture output survives a restart, not just the mesh output.
            reopened_texture_outputs = _reopen_outputs(queue_jobs[texture_job.job_id], interface)
            self.assertEqual(reopened_texture_outputs[TextureProcessingJob.PROCESSED_TEXTURES], processed)

            # The published model's texture bindings resolve to exactly the DDS copies the mesh result names.
            _layers, assets, unresolved_paths = UsdUtils.ComputeAllDependencies(str(final_model))
            resolved_dds = {pathlib.Path(asset).resolve() for asset in assets if pathlib.Path(asset).suffix == ".dds"}
            self.assertEqual(
                resolved_dds, {pathlib.Path(item.asset_url).resolve() for item in result.texture_result.items}
            )
            self.assertTrue(all(path.exists() for path in resolved_dds))
            image_suffixes = {".png", ".jpg", ".jpeg"}
            self.assertFalse(any(pathlib.Path(path).suffix.lower() in image_suffixes for path in unresolved_paths))

            # One resolved DDS is byte-identical to a texture job output: reuse, not re-conversion.
            self.assertTrue(
                any(path.read_bytes() == published.read_bytes() for path in resolved_dds for published in published_dds)
            )

            # The durable optimized-mesh output reconstructs through a fresh queue interface.
            self.assertEqual(
                _reopen_outputs(queue_jobs[mesh_job.job_id], interface)[MeshOptimizationJob.OPTIMIZED_MESH],
                outputs[MeshOptimizationJob.OPTIMIZED_MESH],
            )

    async def test_mesh_job_without_textures_keeps_materialized_textures_unconverted(self):
        """A mesh job bound to an empty texture result publishes the model with its authored textures as-is."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            texture_path = temp_path / "textures" / "albedo.png"
            texture_path.parent.mkdir(parents=True)
            shutil.copy2(_get_normal_fixture_path(), texture_path)
            model_work_path = temp_path / "prepared" / "model.usda"
            model_work_path.parent.mkdir(parents=True)
            model_work_path.write_text(_make_model_usda(texture_path))
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Mesh optimization without textures")
            mesh_job = MeshOptimizationJob(name="Optimize mesh")
            graph.add_job(mesh_job)
            graph.bind(
                mesh_job,
                MeshOptimizationJob.SOURCE_MODEL,
                PrepareOptimizationResult(
                    model_work_path=model_work_path,
                    texture_items=(),
                    referenced_layers=(),
                    texture_ledger=(),
                    source_path=model_work_path,
                    source_root=temp_path,
                ),
            )
            graph.bind(mesh_job, MeshOptimizationJob.TEXTURE_INPUT, TextureProcessingResult(items=()))
            queue_job = interface.submit(graph)[0]

            # Run the real scheduler through the standalone mesh-optimization job.
            outputs = await _run_until_outputs(queue_job, interface)

            # The job completes and publishes the prepared model as-is.
            self.assertIs(queue_job.snapshot().state, JobState.DONE)
            final_model = pathlib.Path(outputs[MeshOptimizationJob.OPTIMIZED_MESH].asset_url)
            self.assertTrue(final_model.is_file())
            self.assertEqual(final_model.suffix, ".usd")

            # The authored texture reference stays unconverted and resolves to the existing source file.
            _layers, assets, unresolved_paths = UsdUtils.ComputeAllDependencies(str(final_model))
            resolved_assets = {pathlib.Path(asset).resolve() for asset in assets}
            self.assertTrue(any(p.suffix == ".png" for p in resolved_assets), f"No PNG textures in {resolved_assets}")
            self.assertTrue(all(path.exists() for path in resolved_assets))

    async def test_connected_graph_lineage_covers_model_sub_usd_and_textures(self):
        """The complete graph lineage records the model, every sub-USD layer, and every texture."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)

            # Build a multi-layer USD fixture: root model references a sub-layer, which references a texture.
            textures_dir = temp_path / "textures"
            textures_dir.mkdir()
            tex_path = textures_dir / "albedo.png"
            shutil.copy2(_get_normal_fixture_path(), tex_path)

            sub_layer_path = temp_path / "sub_layer.usda"
            sub_layer_path.write_text(
                _make_model_usda(tex_path),
                encoding="utf-8",
            )

            model_path = temp_path / "model.usda"
            model_path.write_text(
                """#usda 1.0
(
    subLayers = [
        @./sub_layer.usda@
    ]
)
"""
            )

            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Multi-layer lineage processing")
            prepare_job = PrepareOptimizationJob(name="Prepare model")
            texture_job = TextureProcessingJob(name="Optimize textures")
            mesh_job = MeshOptimizationJob(name="Optimize mesh")
            graph.add_job(prepare_job)
            graph.add_job(texture_job)
            graph.add_job(mesh_job)
            graph.bind(
                prepare_job,
                PrepareOptimizationJob.SOURCE_MODEL,
                MeshOptimizationRequest(
                    source_path=model_path,
                    source_root=temp_path,
                ),
            )
            graph.connect(
                prepare_job.output(PrepareOptimizationJob.TEXTURE_REQUEST),
                texture_job.input(TextureProcessingJob.SOURCE_TEXTURES),
            )
            graph.connect(
                prepare_job.output(PrepareOptimizationJob.PREPARED_MESH),
                mesh_job.input(MeshOptimizationJob.SOURCE_MODEL),
            )
            graph.connect(
                texture_job.output(TextureProcessingJob.PROCESSED_TEXTURES),
                mesh_job.input(MeshOptimizationJob.TEXTURE_INPUT),
            )

            queue_jobs = {queue_job.job_id: queue_job for queue_job in interface.submit(graph)}
            outputs = await _run_until_outputs(queue_jobs[mesh_job.job_id], interface)

            self.assertIs(queue_jobs[mesh_job.job_id].snapshot().state, JobState.DONE)
            result = outputs[MeshOptimizationJob.OPTIMIZED_MESH]
            self.assertIsInstance(result, MeshOptimizationResult)

            # Lineage must contain at least: model + sub-layer + texture.
            self.assertGreaterEqual(len(result.lineage), 3, f"Expected >=3 lineage entries, got {result.lineage}")

            # Every source_hash is non-blank.
            for entry in result.lineage:
                self.assertTrue(entry[2].strip(), f"Blank source_hash in {entry}")
                self.assertTrue(entry[0].strip(), f"Blank source_path in {entry}")
                self.assertTrue(entry[1].strip(), f"Blank output_path in {entry}")

            # The model is the first entry.
            self.assertEqual(result.lineage[0][0], str(model_path))
            model_output = pathlib.Path(result.lineage[0][1])
            self.assertTrue(model_output.is_file())
            self.assertEqual(model_output.suffix, ".usd")

            # The model lineage entry hashes the original USD source, not the published (converted) output.
            self.assertEqual(result.lineage[0][2], hash_file(str(model_path)))
            self.assertNotEqual(model_path.read_bytes(), model_output.read_bytes())
            self.assertNotEqual(result.lineage[0][2], hash_file(str(model_output)))

            # At least one sub-USD layer entry references sub_layer.usda.
            sub_usd_sources = {entry[0] for entry in result.lineage if entry[0].endswith("sub_layer.usda")}
            self.assertTrue(sub_usd_sources, "No sub-USD layer entry for sub_layer.usda")

            # Each sub-USD lineage entry hashes the durable, unmutated copy this job received from
            # PrepareOptimizationJob, not the published copy that texture-reference rewriting mutated.
            prepared = interface.get_job_outputs(prepare_job.job_id)[PrepareOptimizationJob.PREPARED_MESH]
            prepared_layers, _prepared_assets, _prepared_unresolved = UsdUtils.ComputeAllDependencies(
                str(prepared.model_work_path)
            )
            prepared_sub_layer = next(
                pathlib.Path(layer.realPath)
                for layer in prepared_layers
                if layer.realPath and pathlib.Path(layer.realPath).name == "sub_layer.usda"
            )
            sub_usd_entry = next(entry for entry in result.lineage if entry[0].endswith("sub_layer.usda"))
            self.assertEqual(sub_usd_entry[2], hash_file(str(prepared_sub_layer)))
            published_sub_layer = pathlib.Path(sub_usd_entry[1])
            self.assertNotEqual(prepared_sub_layer.read_bytes(), published_sub_layer.read_bytes())
            self.assertNotEqual(sub_usd_entry[2], hash_file(str(published_sub_layer)))

            # At least one texture entry references a DDS output.
            dds_outputs = [entry for entry in result.lineage if entry[1].endswith(".dds")]
            self.assertTrue(dds_outputs, "No texture lineage entry with DDS output")

            # Every texture lineage entry has a non-blank source_hash.
            for entry in dds_outputs:
                self.assertTrue(entry[2].strip())

            # Every texture lineage entry is carried up with its source and hash intact, and its output
            # re-based onto the copy published beside the model.
            texture_outputs = interface.get_job_outputs(texture_job.job_id)[TextureProcessingJob.PROCESSED_TEXTURES]
            self.assertTrue(texture_outputs.lineage)
            texture_lineage_in_mesh = [
                entry for entry in result.lineage if entry[0] in {e[0] for e in texture_outputs.lineage}
            ]
            self.assertEqual(
                [(entry[0], entry[2]) for entry in texture_lineage_in_mesh],
                [(entry[0], entry[2]) for entry in texture_outputs.lineage],
            )
            for entry in texture_lineage_in_mesh:
                self.assertTrue(pathlib.Path(entry[1]).is_relative_to(model_output.parent), entry[1])
                self.assertTrue(pathlib.Path(entry[1]).is_file(), entry[1])

    async def test_graph_publishes_model_with_dds_bindings(self):
        """A published model stage keeps its authored topology and carries final DDS bindings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_model = _get_textured_fbx_fixture_path()
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Textured FBX publication")
            prepare_job = PrepareOptimizationJob(name="Prepare optimization")
            texture_job = TextureProcessingJob(name="Optimize textures")
            mesh_job = MeshOptimizationJob(name="Optimize mesh")
            graph.add_job(prepare_job)
            graph.add_job(texture_job)
            graph.add_job(mesh_job)
            graph.bind(
                prepare_job,
                PrepareOptimizationJob.SOURCE_MODEL,
                MeshOptimizationRequest(
                    source_path=source_model,
                    source_root=source_model.parent,
                ),
            )
            graph.connect(
                prepare_job.output(PrepareOptimizationJob.TEXTURE_REQUEST),
                texture_job.input(TextureProcessingJob.SOURCE_TEXTURES),
            )
            graph.connect(
                prepare_job.output(PrepareOptimizationJob.PREPARED_MESH),
                mesh_job.input(MeshOptimizationJob.SOURCE_MODEL),
            )
            graph.connect(
                texture_job.output(TextureProcessingJob.PROCESSED_TEXTURES),
                mesh_job.input(MeshOptimizationJob.TEXTURE_INPUT),
            )

            queue_jobs = {queue_job.job_id: queue_job for queue_job in interface.submit(graph)}
            outputs = await _run_until_outputs(queue_jobs[mesh_job.job_id], interface)

            result = outputs[MeshOptimizationJob.OPTIMIZED_MESH]
            self.assertIsInstance(result, MeshOptimizationResult)
            final_model = pathlib.Path(result.asset_url)
            final_stage = Usd.Stage.Open(str(final_model))

            self.assertIsNotNone(final_stage)
            self.assertGreater(_count_meshes(final_stage), 0)
            self.assertTrue(_all_meshes_keep_authored_quads(final_stage))
            self.assertTrue(_all_materials_use_aperture_pbr(final_stage))
            # The meta step wraps every published root prim under ReferenceTarget/XForms, so
            # bindings captured earlier in the pipeline resolve one level deeper in the final stage.
            _layers, assets, _unresolved = UsdUtils.ComputeAllDependencies(str(final_model))
            dds_assets = [a for a in assets if pathlib.Path(a).suffix == ".dds"]
            self.assertTrue(dds_assets)
            for asset_path in dds_assets:
                self.assertTrue(_resolve_relative_asset_path(final_model, asset_path).exists(), asset_path)

    async def test_graph_publishes_collected_sub_usd_dependencies(self):
        """Publication includes sub-USD dependencies collected during standardization, not just the root."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_model = _write_two_layer_model(temp_path)
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Sub-USD dependency collection")
            prepare_job = PrepareOptimizationJob(name="Prepare optimization")
            texture_job = TextureProcessingJob(name="Optimize textures")
            mesh_job = MeshOptimizationJob(name="Optimize mesh")
            graph.add_job(prepare_job)
            graph.add_job(texture_job)
            graph.add_job(mesh_job)
            graph.bind(
                prepare_job,
                PrepareOptimizationJob.SOURCE_MODEL,
                MeshOptimizationRequest(
                    source_path=source_model,
                    source_root=source_model.parent,
                ),
            )
            graph.connect(
                prepare_job.output(PrepareOptimizationJob.TEXTURE_REQUEST),
                texture_job.input(TextureProcessingJob.SOURCE_TEXTURES),
            )
            graph.connect(
                prepare_job.output(PrepareOptimizationJob.PREPARED_MESH),
                mesh_job.input(MeshOptimizationJob.SOURCE_MODEL),
            )
            graph.connect(
                texture_job.output(TextureProcessingJob.PROCESSED_TEXTURES),
                mesh_job.input(MeshOptimizationJob.TEXTURE_INPUT),
            )

            queue_jobs = {queue_job.job_id: queue_job for queue_job in interface.submit(graph)}
            outputs = await _run_until_outputs(queue_jobs[mesh_job.job_id], interface)

            result = outputs[MeshOptimizationJob.OPTIMIZED_MESH]
            self.assertIsInstance(result, MeshOptimizationResult)
            final_model = pathlib.Path(result.asset_url)
            child_layer = final_model.parent / "SubUSDs" / "child.usda"

            self.assertTrue(final_model.exists())
            self.assertTrue(child_layer.exists())

            final_stage = Usd.Stage.Open(str(final_model))
            self.assertIsNotNone(final_stage)
            all_layers, assets, unresolved_paths = UsdUtils.ComputeAllDependencies(str(final_model))
            dependency_paths = {pathlib.Path(layer.realPath).resolve() for layer in all_layers if layer.realPath}
            self.assertIn(child_layer.resolve(), dependency_paths)

            self.assertFalse(any(pathlib.Path(path).suffix == ".png" for path in unresolved_paths))

            resolved_dds_paths = {
                pathlib.Path(asset).resolve() for asset in assets if pathlib.Path(asset).suffix == ".dds"
            }
            for item in result.texture_result.items:
                self.assertIn(pathlib.Path(item.asset_url).resolve(), resolved_dds_paths)

    async def test_graph_keeps_stable_dependency_outputs_across_fbx_runs(self):
        """Imported model dependencies keep stable source identities across independent runs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_model = _get_textured_fbx_fixture_path()
            completed_paths = []

            for _run_index in range(2):
                interface = QueueInterface(str(temp_path / f"queue_{_run_index}.sqlite"))
                graph = JobGraph(name=f"FBX run {_run_index}")
                prepare_job = PrepareOptimizationJob(name="Prepare optimization")
                texture_job = TextureProcessingJob(name="Optimize textures")
                mesh_job = MeshOptimizationJob(name="Optimize mesh")
                graph.add_job(prepare_job)
                graph.add_job(texture_job)
                graph.add_job(mesh_job)
                graph.bind(
                    prepare_job,
                    PrepareOptimizationJob.SOURCE_MODEL,
                    MeshOptimizationRequest(
                        source_path=source_model,
                        source_root=source_model.parent,
                    ),
                )
                graph.connect(
                    prepare_job.output(PrepareOptimizationJob.TEXTURE_REQUEST),
                    texture_job.input(TextureProcessingJob.SOURCE_TEXTURES),
                )
                graph.connect(
                    prepare_job.output(PrepareOptimizationJob.PREPARED_MESH),
                    mesh_job.input(MeshOptimizationJob.SOURCE_MODEL),
                )
                graph.connect(
                    texture_job.output(TextureProcessingJob.PROCESSED_TEXTURES),
                    mesh_job.input(MeshOptimizationJob.TEXTURE_INPUT),
                )
                queue_jobs = {queue_job.job_id: queue_job for queue_job in interface.submit(graph)}
                outputs = await _run_until_outputs(queue_jobs[mesh_job.job_id], interface)
                result = outputs[MeshOptimizationJob.OPTIMIZED_MESH]
                self.assertIsInstance(result, MeshOptimizationResult)
                completed_paths.append(tuple(pathlib.Path(item.asset_url).name for item in result.texture_result.items))

            # Both runs produce the same output filenames, proving stable dependency identity.
            self.assertEqual(completed_paths[0], completed_paths[1])
            self.assertTrue(completed_paths[0])
            self.assertFalse(any("_external" in name for name in completed_paths[0]))

    async def test_graph_keeps_stable_dependency_outputs_across_usd_runs(self):
        """Collected USD dependencies keep their project-relative identity across runs."""
        async with open_test_project(_PROJECT_STAGE, context_name=_RESOURCE_CONTEXT) as project_url:
            stage = omni.usd.get_context(_RESOURCE_CONTEXT).get_stage()
            self.assertIsNotNone(stage)
            shader = UsdShade.Shader(stage.GetPrimAtPath("/RootNode/Looks/transfer_workflow_material/Shader"))
            self.assertTrue(shader)
            shader.CreateIdAttr("UsdPreviewSurface")
            stage.GetEditTarget().GetLayer().Save()
            with tempfile.TemporaryDirectory() as temp_dir:
                source_model = pathlib.Path(project_url.path)
                source_root = source_model.parent
                completed_paths = []

                for _run_index in range(2):
                    interface = QueueInterface(str(pathlib.Path(temp_dir) / f"queue_{_run_index}.sqlite"))
                    graph = JobGraph(name=f"USD run {_run_index}")
                    prepare_job = PrepareOptimizationJob(name="Prepare optimization")
                    texture_job = TextureProcessingJob(name="Optimize textures")
                    mesh_job = MeshOptimizationJob(name="Optimize mesh")
                    graph.add_job(prepare_job)
                    graph.add_job(texture_job)
                    graph.add_job(mesh_job)
                    graph.bind(
                        prepare_job,
                        PrepareOptimizationJob.SOURCE_MODEL,
                        MeshOptimizationRequest(
                            source_path=source_model,
                            source_root=source_root,
                        ),
                    )
                    graph.connect(
                        prepare_job.output(PrepareOptimizationJob.TEXTURE_REQUEST),
                        texture_job.input(TextureProcessingJob.SOURCE_TEXTURES),
                    )
                    graph.connect(
                        prepare_job.output(PrepareOptimizationJob.PREPARED_MESH),
                        mesh_job.input(MeshOptimizationJob.SOURCE_MODEL),
                    )
                    graph.connect(
                        texture_job.output(TextureProcessingJob.PROCESSED_TEXTURES),
                        mesh_job.input(MeshOptimizationJob.TEXTURE_INPUT),
                    )
                    queue_jobs = {queue_job.job_id: queue_job for queue_job in interface.submit(graph)}
                    outputs = await _run_until_outputs(queue_jobs[mesh_job.job_id], interface)
                    result = outputs[MeshOptimizationJob.OPTIMIZED_MESH]
                    self.assertIsInstance(result, MeshOptimizationResult)
                    completed_paths.append(
                        tuple(pathlib.Path(item.asset_url).name for item in result.texture_result.items)
                    )

                # Both runs produce the same output filenames, proving stable dependency identity.
                self.assertEqual(completed_paths[0], completed_paths[1])
                self.assertTrue(completed_paths[0])
                self.assertFalse(any("_external" in name for name in completed_paths[0]))

    async def test_graph_publishes_model_with_converted_textures_and_metadata(self):
        """The graph processes a real textured FBX and publishes the model with DDS references."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_model = _get_textured_fbx_fixture_path()
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Textured FBX publication")
            prepare_job = PrepareOptimizationJob(name="Prepare optimization")
            texture_job = TextureProcessingJob(name="Optimize textures")
            mesh_job = MeshOptimizationJob(name="Optimize mesh")
            graph.add_job(prepare_job)
            graph.add_job(texture_job)
            graph.add_job(mesh_job)
            graph.bind(
                prepare_job,
                PrepareOptimizationJob.SOURCE_MODEL,
                MeshOptimizationRequest(
                    source_path=source_model,
                    source_root=source_model.parent,
                ),
            )
            graph.connect(
                prepare_job.output(PrepareOptimizationJob.TEXTURE_REQUEST),
                texture_job.input(TextureProcessingJob.SOURCE_TEXTURES),
            )
            graph.connect(
                prepare_job.output(PrepareOptimizationJob.PREPARED_MESH),
                mesh_job.input(MeshOptimizationJob.SOURCE_MODEL),
            )
            graph.connect(
                texture_job.output(TextureProcessingJob.PROCESSED_TEXTURES),
                mesh_job.input(MeshOptimizationJob.TEXTURE_INPUT),
            )

            queue_jobs = {queue_job.job_id: queue_job for queue_job in interface.submit(graph)}
            outputs = await _run_until_outputs(queue_jobs[mesh_job.job_id], interface)

            result = outputs[MeshOptimizationJob.OPTIMIZED_MESH]
            self.assertIsInstance(result, MeshOptimizationResult)
            final_model = pathlib.Path(result.asset_url)

            self.assertTrue(final_model.is_file())
            self.assertEqual(final_model.suffix, ".usd")
            self.assertGreater(len(result.texture_result.items), 0)
            for item in result.texture_result.items:
                texture_path = pathlib.Path(item.asset_url)
                self.assertEqual(texture_path.suffix, ".dds")
                self.assertTrue(texture_path.exists(), str(texture_path))
                self.assertEqual(texture_path.read_bytes()[:4], b"DDS ")
            self.assertTrue(any(item.texture_type is TextureTypes.NORMAL_OTH for item in result.texture_result.items))
            # No temporary PNG survives in the output area.
            output_dir = final_model.parent
            self.assertFalse(any(path.suffix == ".png" for path in output_dir.iterdir()))

    async def test_graph_completes_all_three_optimization_phases(self):
        """The graph completes prepare, texture, and mesh jobs for a real FBX."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_model = _get_textured_fbx_fixture_path()
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph = JobGraph(name="Three-phase FBX optimization")
            prepare_job = PrepareOptimizationJob(name="Prepare optimization")
            texture_job = TextureProcessingJob(name="Optimize textures")
            mesh_job = MeshOptimizationJob(name="Optimize mesh")
            graph.add_job(prepare_job)
            graph.add_job(texture_job)
            graph.add_job(mesh_job)
            graph.bind(
                prepare_job,
                PrepareOptimizationJob.SOURCE_MODEL,
                MeshOptimizationRequest(
                    source_path=source_model,
                    source_root=source_model.parent,
                ),
            )
            graph.connect(
                prepare_job.output(PrepareOptimizationJob.TEXTURE_REQUEST),
                texture_job.input(TextureProcessingJob.SOURCE_TEXTURES),
            )
            graph.connect(
                prepare_job.output(PrepareOptimizationJob.PREPARED_MESH),
                mesh_job.input(MeshOptimizationJob.SOURCE_MODEL),
            )
            graph.connect(
                texture_job.output(TextureProcessingJob.PROCESSED_TEXTURES),
                mesh_job.input(MeshOptimizationJob.TEXTURE_INPUT),
            )

            queue_jobs = {queue_job.job_id: queue_job for queue_job in interface.submit(graph)}
            outputs = await _run_until_outputs(queue_jobs[mesh_job.job_id], interface)

            # All three jobs settle.
            for qj in queue_jobs.values():
                self.assertIs(qj.snapshot().state, JobState.DONE)

            result = outputs[MeshOptimizationJob.OPTIMIZED_MESH]
            self.assertIsInstance(result, MeshOptimizationResult)
            # The prepare job discovered textures and layers.
            prepare_job_id = next(job.job_id for job in graph.jobs if isinstance(job, PrepareOptimizationJob))
            prepared = interface.get_job_outputs(prepare_job_id)[PrepareOptimizationJob.PREPARED_MESH]
            self.assertTrue(prepared.texture_items)
            self.assertTrue(prepared.referenced_layers)

            # The texture job published DDS outputs.
            texture_job_id = next(job.job_id for job in graph.jobs if isinstance(job, TextureProcessingJob))
            processed = interface.get_job_outputs(texture_job_id)[TextureProcessingJob.PROCESSED_TEXTURES]
            self.assertTrue(processed.items)
            for item in processed.items:
                self.assertTrue(pathlib.Path(item.asset_url).is_file())
            final_model = pathlib.Path(result.asset_url)
            self.assertTrue(final_model.is_file())
            self.assertEqual(final_model.suffix, ".usd")

            # The published stage proves mesh steps ran: authored topology kept, converted materials, DDS bindings.
            final_stage = Usd.Stage.Open(str(final_model))
            self.assertIsNotNone(final_stage)
            self.assertGreater(_count_meshes(final_stage), 0)
            self.assertTrue(_all_meshes_keep_authored_quads(final_stage))
            self.assertTrue(_all_materials_use_aperture_pbr(final_stage))
            _layers, assets, _unresolved = UsdUtils.ComputeAllDependencies(str(final_model))
            dds_assets = [a for a in assets if pathlib.Path(a).suffix == ".dds"]
            self.assertTrue(dds_assets)

    async def test_apply_and_revert_real_graph_writes_and_deletes_metadata(self):
        """Apply writes complete output metadata and base hashes for model and texture inputs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_texture = temp_path / "source.png"
            shutil.copy2(_get_normal_fixture_path(), source_texture)
            source_model = temp_path / "model.usda"
            source_model.write_text(_make_model_usda(source_texture))
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph, mesh_job = build_asset_optimization_graph(
                MeshOptimizationRequest(
                    source_path=source_model,
                    source_root=temp_path,
                )
            )
            queue_jobs = {queue_job.job_id: queue_job for queue_job in interface.submit(graph)}
            result = (await _run_until_outputs(queue_jobs[mesh_job.job_id], interface))[
                MeshOptimizationJob.OPTIMIZED_MESH
            ]
            mesh_output_path = pathlib.Path(result.asset_url)
            texture_output_paths = [pathlib.Path(item.asset_url) for item in result.texture_result.items]
            output_paths = [mesh_output_path] + texture_output_paths
            input_paths = [result.source_path] + [item.source_path for item in result.texture_result.items]
            never_touched_sidecars = [
                path.with_suffix(path.suffix + ".meta") for path in [mesh_output_path] + input_paths
            ]
            apply_keys = (BASE_HASH_KEY, VALIDATION_PASSED_KEY, VALIDATION_EXTENSIONS_KEY)
            # The mesh model and every consumed input carry no sidecar yet. A converted DDS texture already
            # carries a reuse-cache sidecar from ``ConvertDDSStep``, but none of Apply's own keys.
            self.assertTrue(all(not sidecar.exists() for sidecar in never_touched_sidecars))
            self.assertTrue(all(read_metadata(str(path), key) is None for path in output_paths for key in apply_keys))

            executor = ApplyExecutor(interface, handlers.get_registry())
            try:
                await executor.apply(mesh_job.job_id)
                self.assertIs(
                    interface.get_job_snapshot(mesh_job.job_id).apply_disposition,
                    ApplyDisposition.APPLIED,
                )
                for output_path in output_paths:
                    self.assertEqual(read_metadata(str(output_path), BASE_HASH_KEY), hash_file(str(output_path)))
                    self.assertIs(read_metadata(str(output_path), VALIDATION_PASSED_KEY), True)
                self.assertEqual(
                    read_metadata(str(output_paths[0]), VALIDATION_EXTENSIONS_KEY),
                    _json_round_trip(get_current_validation_extensions()),
                )
                for input_path in input_paths:
                    metadata = json.loads(input_path.with_suffix(input_path.suffix + ".meta").read_text())
                    self.assertEqual(metadata, {BASE_HASH_KEY: hash_file(str(input_path))})

                await executor.revert(mesh_job.job_id)
                self.assertIs(
                    interface.get_job_snapshot(mesh_job.job_id).apply_disposition,
                    ApplyDisposition.DECLINED,
                )
                self.assertTrue(all(not sidecar.exists() for sidecar in never_touched_sidecars))
                self.assertTrue(
                    all(read_metadata(str(path), key) is None for path in output_paths for key in apply_keys)
                )
            finally:
                await executor.shutdown()


def _make_model_usda(texture_path: pathlib.Path) -> str:
    """Build one textured USDA model referencing an existing texture by absolute path.

    Args:
        texture_path: Existing texture file the model's shader references.

    Returns:
        USDA content for one quad with an OmniPBR diffuse texture binding.
    """
    return f"""#usda 1.0
(
    defaultPrim = "Quad"
    metersPerUnit = 1
    upAxis = "Y"
)

def Xform "Quad"
{{
    def Mesh "Quad"
    {{
        uniform bool doubleSided = 1
        float3[] extent = [(-1, 0, -1), (1, 0, 1)]
        int[] faceVertexCounts = [4]
        int[] faceVertexIndices = [0, 1, 2, 3]
        rel material:binding = </Quad/Material> (
            bindMaterialAs = "weakerThanDescendants"
        )
        normal3f[] normals = [(0, 1, 0), (0, 1, 0), (0, 1, 0), (0, 1, 0)] (
            interpolation = "faceVarying"
        )
        point3f[] points = [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)]
        texCoord2f[] primvars:st = [(0, 0), (1, 0), (1, 1), (0, 1)] (
            interpolation = "faceVarying"
        )
        uniform token subdivisionScheme = "none"
    }}

    def Material "Material"
    {{
        token outputs:mdl:surface.connect = </Quad/Material/Shader.outputs:out>

        def Shader "Shader"
        {{
            uniform token info:implementationSource = "sourceAsset"
            uniform asset info:mdl:sourceAsset = @OmniPBR.mdl@
            uniform token info:mdl:sourceAsset:subIdentifier = "OmniPBR"
            asset inputs:diffuse_texture = @{texture_path.as_posix()}@ (
                colorSpace = "auto"
            )
            token outputs:out (
                renderType = "material"
            )
        }}
    }}
}}
"""


async def _run_until_outputs(queue_job, interface: QueueInterface) -> JobOutputs:
    """Run one real scheduler until the selected job returns outputs.

    Args:
        queue_job: Submitted job handle to await.
        interface: Queue containing the job graph.

    Returns:
        Durable typed outputs from the selected job.
    """
    scheduler = JobScheduler(interface)
    scheduler.start()
    try:
        return await queue_job.outputs(timeout=120)
    finally:
        await scheduler.stop()


def _reopen_outputs(queue_job, interface: QueueInterface) -> JobOutputs:
    """Read completed outputs through a fresh queue interface.

    Args:
        queue_job: Completed submitted job handle.
        interface: Queue containing the job graph.

    Returns:
        Freshly reconstructed typed outputs.
    """
    reopened_interface = QueueInterface(interface.db_path)
    return reopened_interface.get_job_outputs(queue_job.job_id)


def _make_texture_request(
    source_paths: tuple[pathlib.Path, ...],
    output_dir: pathlib.Path | str,
    *,
    source_root: pathlib.Path | None = None,
) -> TextureProcessingRequest:
    """Create one real texture-processing request for E2E queue runs.

    Args:
        source_paths: Texture sources in stable order.
        output_dir: Final local or remote publication directory.
        source_root: Stable root used to preserve source-relative output paths.

    Returns:
        Immutable request containing every source texture.
    """
    return TextureProcessingRequest(
        items=tuple(
            TextureProcessingItem(
                key=f"texture_{index}",
                path=source_path,
                texture_type=TextureTypes.NORMAL_DX,
            )
            for index, source_path in enumerate(source_paths, start=1)
        ),
        source_root=source_root or source_paths[0].parent,
        output_url=str(output_dir),
    )


def _get_normal_fixture_path() -> pathlib.Path:
    """Return the repository's real DirectX normal-map fixture.

    Returns:
        Absolute fixture path.
    """
    extension_root = pathlib.Path(
        omni.kit.app.get_app()
        .get_extension_manager()
        .get_extension_path_by_module("omni.flux.utils.octahedral_converter")
    )
    return extension_root / "data" / "tests" / "textures" / "Normal_Map_Test_DirectX.png"


def _get_textured_fbx_fixture_path() -> pathlib.Path:
    """Return the repository's real textured FBX fixture.

    Returns:
        Absolute fixture path.
    """
    extension_root = pathlib.Path(
        omni.kit.app.get_app().get_extension_manager().get_extension_path_by_module("omni.flux.asset_importer.core")
    )
    return (
        extension_root / "data" / "tests" / "SM_Fixture_Elevator_Interior" / "SM_Fixture_Elevator_Interior_Textured.fbx"
    )


def _count_meshes(stage: Usd.Stage) -> int:
    return sum(1 for prim in stage.Traverse() if prim.IsA(UsdGeom.Mesh))


def _all_meshes_keep_authored_quads(stage: Usd.Stage) -> bool:
    """Return True when the fixture's authored quad faces survive: the pipeline never triangulates."""
    face_counts = [
        count
        for prim in stage.Traverse()
        if prim.IsA(UsdGeom.Mesh)
        for count in (UsdGeom.Mesh(prim).GetFaceVertexCountsAttr().Get() or ())
    ]
    return bool(face_counts) and 4 in face_counts


def _all_materials_use_aperture_pbr(stage: Usd.Stage) -> bool:
    """Return True when every material in ``stage`` uses an AperturePBR shader variant.

    The converter selects either AperturePBR shader from each authored input identifier.
    This helper accepts both shader variants.

    Args:
        stage: USD stage to inspect.

    Returns:
        True when every material uses an AperturePBR variant; False otherwise.
    """
    material_prims = [prim for prim in stage.Traverse() if prim.IsA(UsdShade.Material)]
    if not material_prims:
        return False
    for material_prim in material_prims:
        shader_prim = omni.usd.get_shader_from_material(material_prim, get_prim=True)
        if shader_prim is None or not shader_prim.IsValid():
            return False
        subidentifier_attr = shader_prim.GetAttribute("info:mdl:sourceAsset:subIdentifier")
        if not subidentifier_attr or not str(subidentifier_attr.Get()).startswith("AperturePBR_"):
            return False
    return True


def _resolve_relative_asset_path(model_path: pathlib.Path, asset_path: str) -> pathlib.Path:
    texture_path = pathlib.Path(asset_path)
    if texture_path.is_absolute():
        return texture_path
    return model_path.parent / texture_path


def _write_two_layer_model(root: pathlib.Path) -> pathlib.Path:
    """Author a parent layer that references a child layer, each with one textured mesh.

    The published model must carry its sub-USD dependency, so this test needs a real reference
    arc. It builds the smallest stage that has one, rather than borrow the shared project
    fixture, which keeps this extension's tests independent of another extension's test data.

    Args:
        root: Directory that receives the textures and the two layers.

    Returns:
        Path of the parent layer.
    """

    def layer(material: str, extra: str = "") -> str:
        return f"""#usda 1.0
(
    defaultPrim = "Root"
    metersPerUnit = 0.01
    upAxis = "Y"
)

def Scope "Root"
{{
    def Scope "Looks"
    {{
        def Material "{material}"
        {{
            token outputs:mdl:surface.connect = </Root/Looks/{material}/Shader.outputs:out>

            def Shader "Shader"
            {{
                uniform token info:implementationSource = "sourceAsset"
                uniform asset info:mdl:sourceAsset = @OmniPBR.mdl@
                uniform token info:mdl:sourceAsset:subIdentifier = "OmniPBR"
                asset inputs:diffuse_texture = @../textures/albedo.png@
                token outputs:out (
                    renderType = "material"
                )
            }}
        }}
    }}

    def Mesh "Cube" (
        prepend apiSchemas = ["MaterialBindingAPI"]
    )
    {{
        int[] faceVertexCounts = [4, 4, 4, 4, 4, 4]
        int[] faceVertexIndices = [0, 1, 3, 2, 4, 6, 7, 5, 6, 2, 3, 7, 4, 5, 1, 0, 4, 0, 2, 6, 5, 7, 3, 1]
        point3f[] points = [(-50, -50, 50), (50, -50, 50), (-50, 50, 50), (50, 50, 50), (-50, -50, -50), (50, -50, -50), (-50, 50, -50), (50, 50, -50)]
        rel material:binding = </Root/Looks/{material}>
        uniform token subdivisionScheme = "none"
    }}
{extra}}}
"""

    textures = root / "assets" / "textures"
    textures.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_get_normal_fixture_path(), textures / "albedo.png")

    models = root / "assets" / "models"
    models.mkdir(parents=True, exist_ok=True)
    (models / "child.usda").write_text(layer("ChildMaterial"), encoding="utf-8")
    parent = models / "parent.usda"
    parent.write_text(
        layer(
            "ParentMaterial", '\n    def Xform "Child_01" (\n        references = @./child.usda@\n    )\n    {\n    }\n'
        ),
        encoding="utf-8",
    )
    return parent


_PROJECT_STAGE = "usd/project_example/combined.usda"
_RESOURCE_CONTEXT = "asset_pipeline_stable_dependency_project"
