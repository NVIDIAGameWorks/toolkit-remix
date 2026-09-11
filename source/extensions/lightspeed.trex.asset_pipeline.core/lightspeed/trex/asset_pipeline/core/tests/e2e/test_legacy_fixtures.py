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

import carb.tokens
import omni.kit.test
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core import handlers
from omni.flux.job_queue.core.apply_executor import ApplyExecutor
from omni.flux.job_queue.core.execute import JobScheduler
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.utils.common.path_utils import hash_file

from lightspeed.trex.asset_pipeline.core.jobs import TextureProcessingJob, build_texture_optimization_graph
from lightspeed.trex.asset_pipeline.core.jobs.models import TextureProcessingItem, TextureProcessingRequest

# Output the retired validator produced from a 16px_metallic.png whose bytes are the committed 16px.png.
# Its DDS payload comes from an older NVTT build, so it is the oracle for names, sidecar keys, and hashes,
# not for encoder bytes.
_LEGACY_SOURCE = "usd/project_example/sources/textures/16px.png"
_LEGACY_OUTPUT = "usd/project_example/sources/textures/ingested/16px_metallic.m.rtex.dds"
_LEGACY_SOURCE_NAME = "16px_metallic.png"
_LEGACY_META_KEYS = ["src_hash", "base_hash", "validation_passed", "validation_extensions"]


class TestLegacyFixtureParityE2E(omni.kit.test.AsyncTestCase):
    """The new pipeline names, hashes, and reuses textures the way the retired validator did."""

    async def test_metallic_texture_matches_legacy_name_and_hash_contract(self):
        """Converting the legacy source yields the legacy filename, sidecar keys, and source hash."""
        legacy_dds, legacy_meta = _legacy_fixture()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source = temp_path / _LEGACY_SOURCE_NAME
            shutil.copy2(_resource(_LEGACY_SOURCE), source)
            output_dir = temp_path / "processed"

            output = await _process(source, output_dir, temp_path)

            self.assertEqual(output.name, legacy_dds.name)
            meta = _read_meta(output)
            self.assertEqual(list(meta), _LEGACY_META_KEYS)
            self.assertEqual(meta["src_hash"], legacy_meta["src_hash"])
            self.assertEqual(meta["base_hash"], hash_file(str(output)))
            self.assertIs(meta["validation_passed"], True)

    async def test_legacy_ingested_dds_is_reused_without_reencoding(self):
        """A DDS the validator produced, carrying only its legacy sidecar, is kept as-is by the new pipeline."""
        legacy_dds, _legacy_meta = _legacy_fixture()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source = temp_path / _LEGACY_SOURCE_NAME
            shutil.copy2(_resource(_LEGACY_SOURCE), source)
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            existing = output_dir / legacy_dds.name
            shutil.copy2(legacy_dds, existing)
            shutil.copy2(legacy_dds.with_suffix(legacy_dds.suffix + ".meta"), existing.with_suffix(".dds.meta"))
            mtime_before = existing.stat().st_mtime_ns

            output = await _process(source, output_dir, temp_path)

            self.assertEqual(output, existing)
            self.assertEqual(existing.stat().st_mtime_ns, mtime_before)
            self.assertEqual(existing.read_bytes(), legacy_dds.read_bytes())


async def _process(source: pathlib.Path, output_dir: pathlib.Path, temp_path: pathlib.Path) -> pathlib.Path:
    """Run one METALLIC texture through the real queue graph and Apply; return the published DDS path."""
    interface = QueueInterface(str(temp_path / "queue.sqlite"))
    request = TextureProcessingRequest(
        items=(TextureProcessingItem(key="metallic", path=source, texture_type=TextureTypes.METALLIC),),
        source_root=temp_path,
        output_url=str(output_dir),
    )
    graph, texture_job = build_texture_optimization_graph(request)
    queue_job = next(job for job in interface.submit(graph) if job.job_id == texture_job.job_id)
    scheduler = JobScheduler(interface)
    scheduler.start()
    try:
        outputs = await queue_job.outputs(timeout=120)
    finally:
        await scheduler.stop()
    executor = ApplyExecutor(interface, handlers.get_registry())
    try:
        await executor.apply(texture_job.job_id)
    finally:
        await executor.shutdown()
    return pathlib.Path(outputs[TextureProcessingJob.PROCESSED_TEXTURES].items[0].asset_url)


def _legacy_fixture() -> tuple[pathlib.Path, dict]:
    dds = _resource(_LEGACY_OUTPUT)
    return dds, _read_meta(dds)


def _read_meta(path: pathlib.Path) -> dict:
    return json.loads(path.with_suffix(path.suffix + ".meta").read_text(encoding="utf-8"))


def _resource(relative: str) -> pathlib.Path:
    root = pathlib.Path(carb.tokens.get_tokens_interface().resolve("${lightspeed.trex.app.resources}"))
    return root / "data" / "tests" / relative
