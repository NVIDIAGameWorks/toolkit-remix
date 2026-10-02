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

import io
import json
import pathlib
import struct
import tempfile
from unittest.mock import patch

import numpy as np
import omni.kit.test
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.nvtt.core import read_linear_image
from omni.flux.job_queue.core.execute import JobScheduler
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.utils.material_converter.utils import TEXTURE_SOURCE_CHANNEL_CUSTOM_DATA_KEY
from PIL import Image
from pxr import Usd, UsdShade

from lightspeed.trex.asset_pipeline.core import RemixAssetItem, RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core.jobs import (
    MeshOptimizationJob,
    PrepareOptimizationJob,
    TextureOptimizationJob,
    build_asset_optimization_graph,
)
from lightspeed.trex.asset_pipeline.core.jobs.models import MeshOptimizationRequest
from lightspeed.trex.asset_pipeline.core.steps import ExtractTextureChannelStep, StandardizeLinearTexturesStep


class TestGltfMaterialE2E(omni.kit.test.AsyncTestCase):
    """Exercise packed glTF textures through the complete optimization graph."""

    async def test_tripo_glb_optimization_preserves_packed_channels(self):
        """Preserve packed texture channels through mesh optimization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "tripo.glb"
            _write_tripo_glb(source_path)
            interface = QueueInterface(str(temp_path / "queue.sqlite"))
            graph, mesh_job = build_asset_optimization_graph(
                MeshOptimizationRequest(source_path=source_path, source_root=temp_path)
            )
            prepare_job = next(job for job in graph.jobs if isinstance(job, PrepareOptimizationJob))
            texture_job = next(job for job in graph.jobs if isinstance(job, TextureOptimizationJob))
            queue_jobs = {job.job_id: job for job in interface.submit(graph)}
            extracted_pixels = {}
            extract_run = ExtractTextureChannelStep.run

            async def observe_extraction(step, context):
                await extract_run(step, context)
                for item in context.items:
                    for texture in item.textures:
                        for channel in ("g", "b"):
                            # The standardized source is linear float OpenEXR, so the extracted channel is too.
                            if texture.path.name.endswith(f".{channel}.exr"):
                                extracted_pixels[channel] = read_linear_image(texture.path)[0, 0].tolist()

            observer = patch.object(ExtractTextureChannelStep, "run", new=observe_extraction)
            observer.start()
            self.addCleanup(observer.stop)
            scheduler = JobScheduler(interface)
            scheduler.start()
            try:
                prepare_outputs = await queue_jobs[prepare_job.job_id].outputs(timeout=120)
                prepared = prepare_outputs[PrepareOptimizationJob.PREPARED_MESH]
                textures = {item.texture_type: item for item in prepared.texture_items}
                self.assertEqual(
                    set(textures),
                    {TextureTypes.DIFFUSE, TextureTypes.ROUGHNESS, TextureTypes.METALLIC, TextureTypes.NORMAL_OGL},
                )
                self.assertEqual(textures[TextureTypes.ROUGHNESS].channel, "G")
                self.assertEqual(textures[TextureTypes.METALLIC].channel, "B")
                self.assertEqual(textures[TextureTypes.ROUGHNESS].path, textures[TextureTypes.METALLIC].path)
                prepared_stage = Usd.Stage.Open(str(prepared.model_work_path))
                prepared_shader = next(prim for prim in prepared_stage.Traverse() if prim.IsA(UsdShade.Shader))
                self.assertEqual(prepared_shader.GetAttribute("inputs:encoding").Get(), 1)
                for name, channel in (("reflectionroughness_texture", "G"), ("metallic_texture", "B")):
                    self.assertEqual(
                        prepared_shader.GetAttribute(f"inputs:{name}").GetCustomDataByKey(
                            TEXTURE_SOURCE_CHANNEL_CUSTOM_DATA_KEY
                        ),
                        channel,
                    )
                outputs = await queue_jobs[mesh_job.job_id].outputs(timeout=120)
                texture_outputs = await queue_jobs[texture_job.job_id].outputs(timeout=120)
            finally:
                await scheduler.stop()

            processed = texture_outputs[TextureOptimizationJob.PROCESSED_TEXTURES]
            processed_by_type = {item.texture_type: item for item in processed.items}
            roughness = processed_by_type[TextureTypes.ROUGHNESS]
            metallic = processed_by_type[TextureTypes.METALLIC]
            self.assertNotEqual(roughness.asset_url, metallic.asset_url)
            np.testing.assert_allclose(extracted_pixels["g"], [64 / 255, 64 / 255, 64 / 255, 1.0], atol=1e-6)
            np.testing.assert_allclose(extracted_pixels["b"], [192 / 255, 192 / 255, 192 / 255, 1.0], atol=1e-6)

            result = outputs[MeshOptimizationJob.OPTIMIZED_MESH]
            final_model = pathlib.Path(result.asset_url)
            stage = Usd.Stage.Open(str(final_model))
            shaders = [prim for prim in stage.Traverse() if prim.IsA(UsdShade.Shader)]
            self.assertEqual(len(shaders), 1)
            shader = shaders[0]
            self.assertEqual(shader.GetAttribute("info:mdl:sourceAsset:subIdentifier").Get(), "AperturePBR_Opacity")
            self.assertEqual(shader.GetAttribute("inputs:encoding").Get(), 0)
            normal = processed_by_type[TextureTypes.NORMAL_OTH]
            self.assertTrue(normal.asset_url.endswith(".dds"), normal.asset_url)
            normal_asset = shader.GetAttribute("inputs:normalmap_texture").Get()
            self.assertTrue(normal_asset.path.endswith(".dds"), normal_asset.path)
            self.assertTrue((final_model.parent / normal_asset.path).is_file())
            published = []
            for name in ("reflectionroughness_texture", "metallic_texture"):
                attribute = shader.GetAttribute(f"inputs:{name}")
                asset = attribute.Get()
                self.assertTrue(asset.path.endswith(".dds"), asset.path)
                image_path = (final_model.parent / asset.path).resolve()
                self.assertTrue(image_path.is_file(), str(image_path))
                published.append(image_path)
            self.assertNotEqual(*published)
            for prim in stage.Traverse():
                for attribute in prim.GetAttributes():
                    self.assertIsNone(attribute.GetCustomDataByKey(TEXTURE_SOURCE_CHANNEL_CUSTOM_DATA_KEY))


class TestExtractTextureChannelE2E(omni.kit.test.AsyncTestCase):
    """Check channel extraction without material conversion or DDS compression."""

    async def test_extracts_green_and_blue_and_preserves_unmarked_texture(self):
        """Extract packed channels and preserve textures without channel metadata."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source = temp_path / "packed.png"
            Image.new("RGB", (2, 2), (17, 64, 192)).save(source)
            roughness = RemixAssetItem.from_texture(source, TextureTypes.ROUGHNESS)
            metallic = RemixAssetItem.from_texture(source, TextureTypes.METALLIC)
            unmarked = RemixAssetItem.from_texture(source, TextureTypes.DIFFUSE)
            roughness.textures[0].channel = "G"
            metallic.textures[0].channel = "B"
            source_bytes = source.read_bytes()
            async with RemixAssetPipelineContext(
                items=[roughness, metallic, unmarked], work_dir=temp_path / "work"
            ) as context:
                await StandardizeLinearTexturesStep().run(context)
                unmarked_path = unmarked.textures[0].path
                unmarked_bytes = unmarked_path.read_bytes()
                await ExtractTextureChannelStep().run(context)
            self.assertNotEqual(roughness.textures[0].path, metallic.textures[0].path)
            for item, channel, value in ((roughness, "g", 64), (metallic, "b", 192)):
                texture = item.textures[0]
                self.assertTrue(texture.path.name.endswith(f".{channel}.exr"))
                self.assertIsNone(texture.channel)
                np.testing.assert_allclose(
                    read_linear_image(texture.path),
                    np.full((2, 2, 4), (value / 255, value / 255, value / 255, 1.0), dtype="float32"),
                    rtol=0,
                    atol=1e-7,
                )
            self.assertEqual(unmarked.textures[0].path, unmarked_path)
            self.assertEqual(unmarked_path.read_bytes(), unmarked_bytes)
            self.assertIsNone(unmarked.textures[0].channel)
            self.assertEqual(source.read_bytes(), source_bytes)

    async def test_extract_udim_channel_and_factor_preserves_each_tile(self):
        """Extract and scale each prepared tile without losing its value or UDIM identity."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            source = root / "packed.<UDIM>.png"
            for tile, green in ((1001, 64), (1002, 192)):
                Image.new("RGB", (2, 2), (17, green, 255)).save(root / f"packed.{tile}.png")
            item = RemixAssetItem.from_texture(source, TextureTypes.ROUGHNESS)
            texture = item.textures[0]
            texture.channel = "G"
            texture.factor = (0.5,)
            async with RemixAssetPipelineContext(items=[item], work_dir=root / "work") as context:
                await StandardizeLinearTexturesStep().run(context)

                await ExtractTextureChannelStep().run(context)

            self.assertEqual(len(texture.udim_tiles), 2)
            self.assertEqual(texture.path, texture.udim_tiles[0])
            self.assertEqual({tile.parent for tile in texture.udim_tiles}, {texture.path.parent})
            self.assertIsNone(texture.channel)
            self.assertIsNone(texture.factor)
            for tile_path, (tile, value) in zip(texture.udim_tiles, ((1001, 32 / 255), (1002, 96 / 255))):
                self.assertIn(f".{tile}.", tile_path.name)
                self.assertEqual(tile_path.suffix, ".exr")
                np.testing.assert_allclose(
                    read_linear_image(tile_path),
                    np.full((2, 2, 4), (value, value, value, 1.0), dtype="float32"),
                    rtol=0,
                    atol=1e-7,
                )

    async def test_extract_distinct_factors_preserves_each_output(self):
        """Keep separate files when factors differ beyond six significant digits."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source = temp_path / "packed.png"
            Image.new("RGB", (2, 2), (255, 255, 255)).save(source)
            items = [RemixAssetItem.from_texture(source, TextureTypes.ROUGHNESS) for _ in range(2)]
            for item, factor in zip(items, (0.4999999701976776, 0.5000000596046448)):
                item.textures[0].channel = "G"
                item.textures[0].factor = (factor,)
            async with RemixAssetPipelineContext(items=items, work_dir=temp_path / "work") as context:
                await StandardizeLinearTexturesStep().run(context)
                await ExtractTextureChannelStep().run(context)
                self.assertNotEqual(items[0].textures[0].path, items[1].textures[0].path)
                for item, value in zip(items, (0.4999999701976776, 0.5000000596046448)):
                    texture = item.textures[0]
                    self.assertIsNone(texture.channel)
                    self.assertIsNone(texture.factor)
                    np.testing.assert_array_equal(
                        read_linear_image(texture.path),
                        np.full((2, 2, 4), (value, value, value, 1.0), dtype="float32"),
                    )

    async def test_extract_color_factors_preserves_linear_color_and_alpha(self):
        """Multiply linear float color and preserve or multiply linear alpha."""
        cases = (
            ("RGB", (255, 255, 255), (0.5, 0.5, 0.5), (0.5, 0.5, 0.5, 1.0)),
            ("RGBA", (255, 255, 255, 128), (0.5, 0.5, 0.5, 0.5), (0.5, 0.5, 0.5, 64 / 255)),
            ("RGB", (255, 255, 255), (0.5, 0.5, 0.5, 0.5), (0.5, 0.5, 0.5, 0.5)),
        )
        for mode, pixel, factor, expected in cases:
            with self.subTest(mode=mode, factor=factor), tempfile.TemporaryDirectory() as temp_dir:
                temp_path = pathlib.Path(temp_dir)
                source = temp_path / "color.png"
                Image.new(mode, (2, 2), pixel).save(source)
                item = RemixAssetItem.from_texture(source, TextureTypes.DIFFUSE)
                item.textures[0].factor = factor
                async with RemixAssetPipelineContext(items=[item], work_dir=temp_path / "work") as context:
                    await StandardizeLinearTexturesStep().run(context)
                    await ExtractTextureChannelStep().run(context)
                    self.assertIsNone(item.textures[0].factor)
                    np.testing.assert_array_equal(
                        read_linear_image(item.textures[0].path), np.full((2, 2, 4), expected, dtype="float32")
                    )

    async def test_standardize_unreadable_marked_texture_fails_and_keeps_the_record_unchanged(self):
        """Reject unreadable sources during preparation without changing the texture record."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source = temp_path / "broken.png"
            source.write_bytes(b"not an image")
            item = RemixAssetItem.from_texture(source, TextureTypes.ROUGHNESS)
            item.textures[0].channel = "G"
            async with RemixAssetPipelineContext(items=[item], work_dir=temp_path / "work") as context:
                with self.assertRaises(RuntimeError):
                    await StandardizeLinearTexturesStep().run(context)
            self.assertEqual(item.textures[0].path, source)
            self.assertEqual(item.textures[0].channel, "G")


def _write_tripo_glb(path: pathlib.Path) -> None:
    """Write a deterministic textured triangle using the supported Tripo material profile."""
    binary = bytearray()
    buffer_views = []
    payloads = [
        (struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0), 34962),
        (struct.pack("<9f", 0, 0, 1, 0, 0, 1, 0, 0, 1), 34962),
        (struct.pack("<6f", 0, 0, 1, 0, 0, 1), 34962),
        (struct.pack("<3H", 0, 1, 2), 34963),
    ]
    for color in ((80, 120, 160), (17, 64, 192), (128, 128, 255)):
        stream = io.BytesIO()
        Image.new("RGB", (1, 1), color).save(stream, format="PNG")
        payloads.append((stream.getvalue(), None))
    for payload, target in payloads:
        binary.extend(b"\x00" * (-len(binary) % 4))
        view = {"buffer": 0, "byteOffset": len(binary), "byteLength": len(payload)}
        if target is not None:
            view["target"] = target
        buffer_views.append(view)
        binary.extend(payload)
    binary.extend(b"\x00" * (-len(binary) % 4))

    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
                        "indices": 3,
                        "material": 0,
                    }
                ]
            }
        ],
        "materials": [
            {
                "name": "tripo_material",
                "pbrMetallicRoughness": {
                    "baseColorTexture": {"index": 0},
                    "metallicRoughnessTexture": {"index": 1},
                    "baseColorFactor": [1, 1, 1, 1],
                    "metallicFactor": 1,
                    "roughnessFactor": 1,
                },
                "normalTexture": {"index": 2, "scale": 1},
            }
        ],
        "textures": [{"source": 0}, {"source": 1}, {"source": 2}],
        "images": [
            {"bufferView": 4, "mimeType": "image/png"},
            {"bufferView": 5, "mimeType": "image/png"},
            {"bufferView": 6, "mimeType": "image/png"},
        ],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": buffer_views,
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "min": [0, 0, 0],
                "max": [1, 1, 0],
            },
            {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": 3, "type": "VEC2"},
            {"bufferView": 3, "componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
    }
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * (-len(json_chunk) % 4)
    total_length = 12 + 8 + len(json_chunk) + 8 + len(binary)
    path.write_bytes(
        struct.pack("<4sII", b"glTF", 2, total_length)
        + struct.pack("<II", len(json_chunk), 0x4E4F534A)
        + json_chunk
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )
