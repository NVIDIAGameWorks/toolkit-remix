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

from __future__ import annotations

__all__: list[str] = []

import json
import pathlib

import omni.kit.test
from lightspeed.trex.asset_pipeline.core.jobs import MeshOptimizationJob, PrepareOptimizationJob, TextureProcessingJob
from lightspeed.trex.asset_pipeline.core.jobs.models import (
    MeshOptimizationRequest,
    MeshOptimizationResult,
    PrepareOptimizationResult,
    ProcessedTexture,
    TextureLedgerEntry,
    TextureProcessingItem,
    TextureProcessingRequest,
    TextureProcessingResult,
)
from lightspeed.trex.asset_pipeline.core.metadata import MetadataApplyReceipt
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core.serializer import deserialize, serialize


def _processed_texture() -> ProcessedTexture:
    """Create one published texture record with non-empty UDIM tiles.

    Returns:
        A diffuse texture record spanning three UDIM tiles.
    """
    return ProcessedTexture(
        key="texture_0",
        source_path=pathlib.Path("textures/toto.1001.png"),
        asset_url="processed/toto.1001.a.rtex.dds",
        texture_type=TextureTypes.DIFFUSE,
        udim_tiles=(
            "processed/toto.1001.a.rtex.dds",
            "processed/toto.1002.a.rtex.dds",
            "processed/toto.1003.a.rtex.dds",
        ),
    )


class TestCodecAssemblies(omni.kit.test.AsyncTestCase):
    """Compatibility guard for the persisted codec catalog: round-trip identity for every registered type."""

    async def test_every_persisted_type_round_trips_a_non_default_value(self):
        """Every persisted type keeps a non-default value, lineage, false flags, and identity intact."""
        texture_item = TextureProcessingItem(
            key="texture_0", path=pathlib.Path("textures/albedo.png"), texture_type=TextureTypes.ROUGHNESS
        )
        processed = _processed_texture()
        texture_request = TextureProcessingRequest(
            items=(texture_item,),
            source_root=pathlib.Path("models"),
            output_url="omniverse://server/project/processed",
        )
        texture_result = TextureProcessingResult(
            items=(processed,),
            lineage=((str(processed.source_path), processed.asset_url, "tex_hash"),),
            validation_passed=False,
        )
        texture_job = TextureProcessingJob(name="Process chair textures")
        ledger_entry = TextureLedgerEntry(
            material_path="/Root/Material/Shader", texture_type=TextureTypes.DIFFUSE, texture_key="texture_0"
        )
        mesh_request = MeshOptimizationRequest(
            source_path=pathlib.Path("models/chair.fbx"),
            source_root=pathlib.Path("models"),
            output_url="omniverse://server/project/assets/ingested",
            replace_udim_textures_by_empty=False,
        )
        prepare_result = PrepareOptimizationResult(
            model_work_path=pathlib.Path("processed/model.usd"),
            texture_items=(texture_item,),
            referenced_layers=("layer.usd",),
            texture_ledger=(ledger_entry,),
            source_path=pathlib.Path("model.usda"),
            source_root=pathlib.Path("."),
            output_url="omniverse://server/project/assets/ingested",
            replace_udim_textures_by_empty=False,
        )
        mesh_result = MeshOptimizationResult(
            asset_url="/out/model.usd",
            texture_result=texture_result,
            lineage=(("/src/model.usd", "/out/model.usd", "model_hash"),) + texture_result.lineage,
            source_path=pathlib.Path("/src/model.usd"),
            validation_passed=False,
        )
        mesh_job = MeshOptimizationJob(name="Optimize chair mesh")
        prepare_job = PrepareOptimizationJob(name="Prepare chair model")
        receipt = MetadataApplyReceipt(
            prior_meta=(
                (pathlib.Path("models/chair.fbx.meta"), '{"base_hash": "deadbeef"}'),
                (pathlib.Path("models/chair.usd.meta"), None),
            )
        )

        # One round trip per persisted type — the compact replacement for 17 per-codec test files.
        cases = [
            None,
            TextureTypes.NORMAL_DX,
            texture_item,
            processed,
            texture_request,
            texture_result,
            texture_job,
            ledger_entry,
            mesh_request,
            prepare_result,
            mesh_result,
            mesh_job,
            prepare_job,
            receipt,
        ]
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(deserialize(serialize(value)), value)

        # False booleans persist as False, not as a falsy stand-in (0, None) that would break `is` checks downstream.
        self.assertIs(deserialize(serialize(texture_result)).validation_passed, False)
        self.assertIs(deserialize(serialize(mesh_result)).validation_passed, False)
        self.assertIs(deserialize(serialize(mesh_request)).replace_udim_textures_by_empty, False)
        self.assertIs(deserialize(serialize(prepare_result)).replace_udim_textures_by_empty, False)

        # Lineage round-trips as an ordered tuple of 3-tuples, not flattened or reordered.
        self.assertEqual(deserialize(serialize(texture_result)).lineage, texture_result.lineage)
        self.assertEqual(deserialize(serialize(mesh_result)).lineage, mesh_result.lineage)

    async def test_released_texture_payloads_decode_with_field_defaults(self):
        """Released 1.1.x ProcessedTexture and TextureProcessingResult payloads decode with new-field defaults."""
        processed = _processed_texture()
        texture_envelope = json.loads(serialize(processed))
        texture_envelope["value"]["value"] = texture_envelope["value"]["value"][:-1]  # drop udim_tiles: 1.1.x shape
        legacy_texture = deserialize(json.dumps(texture_envelope))
        self.assertEqual(
            legacy_texture,
            ProcessedTexture(
                key=processed.key,
                source_path=processed.source_path,
                asset_url=processed.asset_url,
                texture_type=processed.texture_type,
            ),
        )

        result = TextureProcessingResult(items=(processed,), lineage=(("a", "b", "c"),), validation_passed=False)
        result_envelope = json.loads(serialize(result))
        result_envelope["value"]["value"] = result_envelope["value"]["value"][:1]  # drop lineage/validation: 1.1.x
        legacy_result = deserialize(json.dumps(result_envelope))
        self.assertEqual(legacy_result, TextureProcessingResult(items=(processed,)))

    async def test_texture_payload_arity_outside_released_and_current_shapes_raises(self):
        """A ProcessedTexture or TextureProcessingResult payload of any other length raises ValueError."""
        processed = _processed_texture()
        texture_envelope = json.loads(serialize(processed))
        texture_envelope["value"]["value"] = texture_envelope["value"]["value"][:3]  # neither 4 nor 5 values
        with self.assertRaises(ValueError):
            deserialize(json.dumps(texture_envelope))

        result = TextureProcessingResult(items=(processed,))
        result_envelope = json.loads(serialize(result))
        result_envelope["value"]["value"] = result_envelope["value"]["value"] * 2  # neither 1 nor 3 values
        with self.assertRaises(ValueError):
            deserialize(json.dumps(result_envelope))
