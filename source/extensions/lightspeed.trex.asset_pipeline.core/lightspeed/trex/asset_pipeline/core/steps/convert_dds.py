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

__all__ = ["ConvertDDSStep"]

import pathlib

import carb
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from omni.flux.nvtt.core import encode_dds
from omni.flux.utils.common.path_utils import read_metadata, write_metadata

from ..constants import DDS_SOURCE_HASH_METADATA_KEY, TEXTURE_INFO, TextureInfo
from ..pipeline.context import RemixAssetPipelineContext
from ..pipeline.item import RemixAssetItem, TextureAsset
from ..texture_naming import DDS_SUFFIX, get_dds_stem_suffix
from ..utils import get_source_hash, is_dds_texture
from ..worker import run_in_worker_thread


def _convert_texture(input_path: str, output_path: str, texture_info: TextureInfo) -> None:
    """Encode one texture to DDS in-process using the settings named by `texture_info`.

    Args:
        input_path: Source texture path.
        output_path: Destination DDS path.
        texture_info: Compression format, gamma handling, and mip filter for this texture.

    Raises:
        NvttUnavailableError: If the NVTT library cannot be loaded.
        RuntimeError: If NVTT cannot read the source or write the destination.
    """
    encode_dds(
        pathlib.Path(input_path),
        pathlib.Path(output_path),
        block_format=texture_info.block_format,
        gamma_encoded=texture_info.gamma_encoded,
        mip_filter=texture_info.mip_filter,
    )


def _needs_processing(texture: TextureAsset, context: RemixAssetPipelineContext, encoded: bool) -> bool:
    """Return whether a texture needs encoding or a copy into the workspace.

    Args:
        texture: Texture record to inspect.
        context: Pipeline context carrying the workspace and the force flag.
        encoded: Whether the concrete file of the texture is a DDS file.
    """
    return (
        not encoded
        or context.force_dds_reencode
        or (context.work_dir is not None and not context.is_in_work_dir(texture.path))
    )


def _can_reuse_dds_output(path: str, source_hash: str | None) -> bool:
    """Return whether an existing DDS was converted from the same source texture.

    Matches the legacy ``get_new_hash`` semantics: reuse when the output exists and its
    ``src_hash`` metadata equals the current source reuse key. The semantic letter in the
    output filename already encodes the conversion, so the same path with the same
    source key is the same conversion. A linear source key carries ``LINEAR_SOURCE_HASH_SUFFIX``,
    so a DDS from a linear source with the legacy plain-hash key does not match and encodes again.

    Args:
        path: Existing DDS path to inspect.
        source_hash: Reuse key of the current source texture, if the source exists.

    Returns:
        True when the file exists and its recorded source hash matches.
    """
    if source_hash is None or not pathlib.Path(path).exists():
        return False
    return read_metadata(path, DDS_SOURCE_HASH_METADATA_KEY) == source_hash


def _write_dds_reuse_metadata(path: str, source_hash: str | None) -> None:
    """Write the source hash used to validate later DDS reuse, as the legacy plugin did.

    Args:
        path: DDS path receiving metadata.
        source_hash: Hash of the source texture, if available.
    """
    if source_hash is None:
        return
    write_metadata(path, DDS_SOURCE_HASH_METADATA_KEY, source_hash)


class ConvertDDSStep(PipelineStep):
    """Convert texture records to DDS format using the in-process NVTT encoder."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier."""
        return "convert_dds"

    @property
    def description(self) -> str:
        """Return a human-readable description."""
        return "Optimize textures"

    def should_run(self, context: RemixAssetPipelineContext) -> bool:
        """Return true when a texture needs a workspace DDS output or forced encoding."""
        return any(_needs_processing(texture, context, is_dds_texture(texture)) for texture in context.textures)

    def validate(self, context: PipelineContext) -> list[str]:
        """Validate that the runner provided work and output directories for DDS files."""
        errors = super().validate(context)
        if errors:
            return errors
        errors.extend(context.validate_work_dir(self.name))
        errors.extend(context.validate_output_dir(self.name))
        return errors

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why this step has no work for the already-compatible context."""
        return "all texture records already point to workspace DDS files"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Convert prepared texture records to DDS or reuse an existing DDS output.

        Standardization supplies every concrete UDIM tile. Each texture selects unchanged DDS copies or encoding
        for all its tiles. The force flag selects encoding even for DDS sources in the workspace.
        Non-UDIM textures retain an empty tile ledger.

        Raises:
            NvttUnavailableError: If the NVTT library cannot be loaded.
            RuntimeError: If NVTT cannot read a source texture or write a destination DDS file.
        """
        for texture in context.textures:
            encoded = is_dds_texture(texture)
            if not _needs_processing(texture, context, encoded):
                continue

            copy_encoded = encoded and not context.force_dds_reencode
            semantic_suffix = get_dds_stem_suffix(texture.texture_type)
            udim_source = texture.original_path or texture.path
            dds_paths: list[pathlib.Path] = []
            for tile_path in texture.udim_tiles or (texture.path,):
                if copy_encoded:
                    if texture.udim_tiles:
                        new_path = await self._copy_tile(context, udim_source, tile_path)
                    else:
                        output_path = context.reserve_output_path(
                            tile_path,
                            source_path=texture.source_path,
                            stem_suffix="",
                            suffix=None,
                        )
                        new_path = await run_in_worker_thread(
                            context.copy_to_work_path, tile_path, output_path.work_path
                        )
                    dds_paths.append(new_path)
                    continue

                source_hash = await run_in_worker_thread(get_source_hash, context, tile_path)
                if texture.udim_tiles:
                    new_path = context.get_work_path(
                        udim_source,
                        stem=tile_path.stem,
                        stem_suffix=semantic_suffix,
                        suffix=DDS_SUFFIX,
                    )
                    final_path = context.get_output_path(new_path, source_path=texture.source_path)
                else:
                    output_path = context.reserve_output_path(
                        tile_path,
                        source_path=texture.source_path,
                        stem_suffix=semantic_suffix,
                        suffix=DDS_SUFFIX,
                    )
                    new_path = output_path.work_path
                    final_path = output_path.output_path

                if await run_in_worker_thread(_can_reuse_dds_output, str(final_path), source_hash):
                    carb.log_info(f"[ConvertDDS] Reusing existing {final_path}")
                    await run_in_worker_thread(context.copy_to_work_path, final_path, new_path)
                else:
                    carb.log_info(f"[ConvertDDS] Converting {tile_path} -> {new_path}")
                    await run_in_worker_thread(
                        _convert_texture, str(tile_path), str(new_path), TEXTURE_INFO[texture.texture_type]
                    )
                await run_in_worker_thread(_write_dds_reuse_metadata, str(new_path), source_hash)
                dds_paths.append(new_path)

            texture.path = dds_paths[0]
            if texture.udim_tiles:
                texture.udim_tiles = tuple(dds_paths)

    @staticmethod
    async def _copy_tile(
        context: RemixAssetPipelineContext, udim_source: pathlib.Path, tile_path: pathlib.Path
    ) -> pathlib.Path:
        """Copy one encoded DDS UDIM tile to the workspace unchanged.

        Args:
            context: Pipeline context owning the workspace.
            udim_source: UDIM source path the tiles belong to.
            tile_path: Concrete encoded tile.

        Returns:
            The workspace path of the copied tile.
        """
        tile_work = context.get_work_path(udim_source, stem=tile_path.stem, stem_suffix="", suffix=tile_path.suffix)
        if tile_path == tile_work:
            return tile_work
        carb.log_info(f"[ConvertDDS] Copying encoded DDS tile {tile_path} -> {tile_work}")
        return await run_in_worker_thread(context.copy_to_work_path, tile_path, tile_work)
