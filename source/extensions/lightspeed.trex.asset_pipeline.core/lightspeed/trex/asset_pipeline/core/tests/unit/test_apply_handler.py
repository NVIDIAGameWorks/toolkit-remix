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

import asyncio
import hashlib
import json
import pathlib
import tempfile
from unittest.mock import patch

import omni.kit.test
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.utils.common.path_utils import hash_file, read_metadata

import lightspeed.trex.asset_pipeline.core.jobs.apply_handler as apply_handler_module
import lightspeed.trex.asset_pipeline.core.metadata as metadata_module
from lightspeed.trex.asset_pipeline.core.jobs.apply_handler import (
    SaveMeshMetadataHandler,
    SaveTextureMetadataHandler,
)
from lightspeed.trex.asset_pipeline.core.jobs.models import (
    MeshOptimizationResult,
    ProcessedTexture,
    TextureProcessingResult,
)


def _texture_result(
    temp_path: pathlib.Path,
    output_paths: tuple[pathlib.Path, ...],
    validation_passed: bool = True,
) -> TextureProcessingResult:
    """Build one texture batch result with the given outputs and pipeline outcome.

    Args:
        temp_path: Directory that holds the synthetic source textures.
        output_paths: Local processed outputs of the batch.
        validation_passed: Pipeline outcome recorded on the result.

    Returns:
        Immutable texture batch result.
    """
    return TextureProcessingResult(
        items=tuple(
            ProcessedTexture(
                key=f"texture_{index}",
                source_path=temp_path / f"source_{index}.png",
                asset_url=str(output_path),
                texture_type=TextureTypes.DIFFUSE,
            )
            for index, output_path in enumerate(output_paths)
        ),
        validation_passed=validation_passed,
    )


class TestApplyHandler(omni.kit.test.AsyncTestCase):
    """Test the metadata Apply boundary."""

    async def test_save_texture_handler_name_input_type_target_type_receipt_type_apply_policy(self):
        """SaveTextureMetadataHandler exposes the exact queue registry fields."""
        # Assert
        self.assertEqual(SaveTextureMetadataHandler.name, "SaveTextureMetadataHandler")
        self.assertEqual(SaveTextureMetadataHandler.input_type, TextureProcessingResult)
        self.assertIs(SaveTextureMetadataHandler.target_type, type(None))
        self.assertEqual(SaveTextureMetadataHandler.receipt_type.__name__, "MetadataApplyReceipt")
        self.assertEqual(SaveTextureMetadataHandler.apply_policy.value, "always_automatic")

    async def test_save_mesh_handler_name_input_type_target_type_receipt_type_apply_policy(self):
        """SaveMeshMetadataHandler exposes the exact queue registry fields."""
        # Assert
        self.assertEqual(SaveMeshMetadataHandler.name, "SaveMeshMetadataHandler")
        self.assertEqual(SaveMeshMetadataHandler.input_type, MeshOptimizationResult)
        self.assertIs(SaveMeshMetadataHandler.target_type, type(None))
        self.assertEqual(SaveMeshMetadataHandler.receipt_type.__name__, "MetadataApplyReceipt")
        self.assertEqual(SaveMeshMetadataHandler.apply_policy.value, "always_automatic")

    async def test_apply_failure_restores_every_sidecar_written_in_attempt(self):
        """A later output write failure removes earlier input and output sidecar changes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_paths = (temp_path / "albedo.dds", temp_path / "normal.dds")
            for index, output_path in enumerate(output_paths):
                output_path.write_bytes(b"DDS ")
                (temp_path / f"source_{index}.png").write_bytes(b"source")
            result = _texture_result(temp_path, output_paths)
            handler = SaveTextureMetadataHandler()
            receipt = await handler.capture_receipt(result, None)

            def fail_after_first_output(paths, _extensions, _validation_passed=True):
                pathlib.Path(f"{paths[0]}.meta").write_text('{"partial": true}')
                raise RuntimeError("injected output metadata failure")

            with patch.object(
                apply_handler_module,
                "write_metadata_for_paths",
                side_effect=fail_after_first_output,
            ):
                # Act
                with self.assertRaisesRegex(RuntimeError, "injected output metadata failure"):
                    await handler.apply(result, None, receipt)

            # Assert
            for path in (*output_paths, temp_path / "source_0.png", temp_path / "source_1.png"):
                self.assertFalse(pathlib.Path(f"{path}.meta").exists())

    async def test_apply_cancellation_restores_every_sidecar_written_in_attempt(self):
        """Cancellation after a partial write restores all input and output sidecars."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_path = temp_path / "albedo.dds"
            output_path.write_bytes(b"DDS ")
            source_path = temp_path / "source_0.png"
            source_path.write_bytes(b"source")
            result = _texture_result(temp_path, (output_path,))
            handler = SaveTextureMetadataHandler()
            receipt = await handler.capture_receipt(result, None)

            def cancel_after_output(paths, _extensions, _validation_passed=True):
                pathlib.Path(f"{paths[0]}.meta").write_text('{"partial": true}')
                raise asyncio.CancelledError

            with patch.object(
                apply_handler_module,
                "write_metadata_for_paths",
                side_effect=cancel_after_output,
            ):
                # Act
                with self.assertRaises(asyncio.CancelledError):
                    await handler.apply(result, None, receipt)

            # Assert
            self.assertFalse(pathlib.Path(f"{output_path}.meta").exists())
            self.assertFalse(pathlib.Path(f"{source_path}.meta").exists())

    async def test_apply_writes_and_reverts_remote_output_metadata(self):
        """A remote processed texture receives and reverts its sidecar through omni.client."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            local_path = temp_path / "albedo.dds"
            local_path.write_bytes(b"DDS local")
            remote_url = "omniverse://server/project/processed/remote.dds"
            remote_meta_url = f"{remote_url}.meta"
            remote_files = {remote_url: b"DDS remote"}
            original_read_file = metadata_module.omni.client.read_file
            original_write_file = metadata_module.omni.client.write_file

            def read_file(url):
                if not url.startswith("omniverse://"):
                    return original_read_file(url)
                content = remote_files.get(url)
                if content is None:
                    return metadata_module.omni.client.Result.ERROR_NOT_FOUND, None, None
                return metadata_module.omni.client.Result.OK, None, content

            def write_file(url, content):
                if not url.startswith("omniverse://"):
                    return original_write_file(url, content)
                remote_files[url] = bytes(content)
                return metadata_module.omni.client.Result.OK

            def delete_file(url):
                remote_files.pop(url, None)
                return metadata_module.omni.client.Result.OK

            result = TextureProcessingResult(
                items=(
                    ProcessedTexture(
                        key="texture_0",
                        source_path=temp_path / "source_0.png",
                        asset_url=remote_url,
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                    ProcessedTexture(
                        key="texture_1",
                        source_path=temp_path / "source_1.png",
                        asset_url=str(local_path),
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                )
            )
            handler = SaveTextureMetadataHandler()

            with (
                patch.object(metadata_module.omni.client, "read_file", side_effect=read_file),
                patch.object(metadata_module.omni.client, "write_file", side_effect=write_file),
                patch.object(metadata_module.omni.client, "delete", side_effect=delete_file),
            ):
                receipt = await handler.capture_receipt(result, None)

                # Act
                await handler.apply(result, None, receipt)

                # Assert
                self.assertEqual(
                    receipt.prior_meta,
                    (
                        (remote_meta_url, None),
                        (local_path.with_suffix(".dds.meta"), None),
                        (temp_path / "source_0.png.meta", None),
                        (temp_path / "source_1.png.meta", None),
                    ),
                )
                remote_meta = json.loads(remote_files[remote_meta_url])
                self.assertEqual(remote_meta["base_hash"], hashlib.md5(b"DDS remote").hexdigest())
                self.assertIs(remote_meta["validation_passed"], True)
                self.assertEqual(read_metadata(str(local_path), "base_hash"), hash_file(str(local_path)))

                await handler.revert(result, None, receipt)

            self.assertNotIn(remote_meta_url, remote_files)
            self.assertFalse(local_path.with_suffix(".dds.meta").exists())

    async def test_apply_writes_and_reverts_remote_mesh_metadata(self):
        """A remote mesh and its texture receive reversible sidecars."""
        # Arrange
        mesh_url = "omniverse://server/project/processed/mesh.usd"
        texture_url = "omniverse://server/project/processed/albedo.diffuse.dds"
        remote_files = {mesh_url: b"usd", texture_url: b"dds"}

        def read_file(url):
            content = remote_files.get(url)
            if content is None:
                return metadata_module.omni.client.Result.ERROR_NOT_FOUND, None, None
            return metadata_module.omni.client.Result.OK, None, content

        def write_file(url, content):
            remote_files[url] = bytes(content)
            return metadata_module.omni.client.Result.OK

        def delete_file(url):
            remote_files.pop(url, None)
            return metadata_module.omni.client.Result.OK

        result = MeshOptimizationResult(
            asset_url=mesh_url,
            texture_result=TextureProcessingResult(
                items=(
                    ProcessedTexture(
                        key="albedo",
                        source_path=pathlib.Path("C:/queue/albedo.png"),
                        asset_url=texture_url,
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                )
            ),
        )
        handler = SaveMeshMetadataHandler()

        with (
            patch.object(metadata_module.omni.client, "read_file", side_effect=read_file),
            patch.object(metadata_module.omni.client, "write_file", side_effect=write_file),
            patch.object(metadata_module.omni.client, "delete", side_effect=delete_file),
        ):
            receipt = await handler.capture_receipt(result, None)

            # Act
            await handler.apply(result, None, receipt)

            # Assert
            self.assertEqual(
                receipt.prior_meta,
                (
                    (f"{mesh_url}.meta", None),
                    (f"{texture_url}.meta", None),
                    (pathlib.Path("C:/queue/albedo.png.meta"), None),
                ),
            )
            self.assertEqual(json.loads(remote_files[f"{mesh_url}.meta"])["base_hash"], hashlib.md5(b"usd").hexdigest())
            self.assertEqual(
                json.loads(remote_files[f"{texture_url}.meta"])["base_hash"], hashlib.md5(b"dds").hexdigest()
            )

            await handler.revert(result, None, receipt)

        self.assertNotIn(f"{mesh_url}.meta", remote_files)
        self.assertNotIn(f"{texture_url}.meta", remote_files)
