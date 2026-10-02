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
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP, TextureTypes
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from omni.flux.nvtt.core import encode_dds, is_linear_image
from omni.flux.utils.common.path_utils import (
    get_udim_sequence as _get_udim_sequence,
    hash_file,
    is_udim_texture as _is_udim_texture,
    read_metadata,
    write_metadata,
)

from ..constants import DDS_SOURCE_HASH_METADATA_KEY, TEXTURE_INFO, TextureInfo
from ..pipeline.context import RemixAssetPipelineContext
from ..pipeline.item import RemixAssetItem
from ..texture_naming import DDS_SUFFIX, get_dds_stem_suffix
from ..worker import run_in_worker_thread

# DDS files from a linear source (OpenEXR or Radiance HDR) written before this version skipped the linear-to-sRGB
# conversion. The different reuse key makes these outputs encode again one time.
LINEAR_SOURCE_HASH_SUFFIX = "-linear-srgb"


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


def _is_encoded_dds(path: pathlib.Path, context: RemixAssetPipelineContext) -> bool:
    """Return whether a source file is an encoded DDS the step copies unchanged.

    Args:
        path: Source texture or UDIM tile path.
        context: Pipeline context carrying ``force_dds_reencode``.

    Returns:
        True for a ``.dds`` source unless the context forces a re-encode.
    """
    return path.suffix.lower() == ".dds" and not context.force_dds_reencode


def _get_texture_info(texture_type: TextureTypes) -> TextureInfo:
    """Look up the texture info for one texture semantic.

    Args:
        texture_type: Texture semantic selecting compression settings.

    Returns:
        The texture's compression format, gamma handling, and mip filter.
    """
    texture_info = TEXTURE_INFO.get(texture_type)
    if texture_info is None:
        # Diffuse is the safest general-purpose encoding for new texture channels that lack explicit TEXTURE_INFO.
        input_name = TEXTURE_TYPE_INPUT_MAP[texture_type]
        carb.log_warn(f"[ConvertDDS] No TEXTURE_INFO for '{input_name}', falling back to DIFFUSE settings")
        texture_info = TEXTURE_INFO[TextureTypes.DIFFUSE]
    return texture_info


def _hash_existing_file(path: str) -> str | None:
    """Return the DDS reuse key of a source file when the path exists locally.

    The key is the file hash. A linear source (OpenEXR or Radiance HDR) adds ``LINEAR_SOURCE_HASH_SUFFIX``.

    Args:
        path: Candidate local file path.

    Returns:
        The reuse key, or ``None`` when the file is absent.
    """
    source = pathlib.Path(path)
    if not source.exists():
        return None
    file_hash = hash_file(path)
    return file_hash + LINEAR_SOURCE_HASH_SUFFIX if is_linear_image(source) else file_hash


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
        """Return true when any texture record still needs a workspace DDS output.

        A UDIM texture (detected by its path pattern or a non-empty ledger) always needs
        processing because its concrete tiles must be converted or copied.
        """
        for texture in context.textures:
            if texture.udim_tiles:
                return True
            if _is_udim_texture(str(texture.path)):
                return True
            # An encoded DDS is copied, never re-encoded, unless the context forces it.
            if not _is_encoded_dds(texture.path, context):
                return True
            if context.work_dir and not context.is_in_work_dir(texture.path):
                return True
        return False

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
        """Convert texture records to DDS or reuse an existing DDS output.

        A UDIM texture carries concrete tiles in ``udim_tiles`` from an earlier step such as
        ``ConvertNormalStep``, or expands fresh tiles from the ``<UDIM>`` source on disk when no
        ledger is set. Every concrete tile converts individually and the ledger is rewritten so
        downstream steps and publication walk every tile.

        Non-UDIM textures follow the original single-path codepath unchanged.

        Raises:
            NvttUnavailableError: If the NVTT library cannot be loaded.
            RuntimeError: If NVTT cannot read a source texture or write a destination DDS file, or if a UDIM
                pattern resolves to zero concrete tile files.
        """
        for texture in context.textures:
            # ---- UDIM path: tiles already in the ledger (from a prior step) ----
            if texture.udim_tiles:
                semantic_suffix = get_dds_stem_suffix(texture.texture_type)
                udim_source = texture.original_path or texture.path
                tile_dds_paths: list[pathlib.Path] = []
                for tile_path in texture.udim_tiles:
                    if _is_encoded_dds(tile_path, context):
                        tile_dds_paths.append(await self._copy_tile(context, udim_source, tile_path))
                        continue
                    source_hash = await run_in_worker_thread(_hash_existing_file, str(tile_path))
                    texture_info = _get_texture_info(texture.texture_type)
                    tile_dds_work = context.get_work_path(
                        udim_source,
                        stem=tile_path.stem,
                        stem_suffix=semantic_suffix,
                        suffix=DDS_SUFFIX,
                    )
                    tile_dds_final = context.get_output_path(tile_dds_work, source_path=texture.source_path)
                    if await run_in_worker_thread(
                        _can_reuse_dds_output,
                        str(tile_dds_final),
                        source_hash,
                    ):
                        carb.log_info(f"[ConvertDDS] Reusing existing {tile_dds_final}")
                        await run_in_worker_thread(context.copy_to_work_path, tile_dds_final, tile_dds_work)
                        await run_in_worker_thread(
                            _write_dds_reuse_metadata,
                            str(tile_dds_work),
                            source_hash,
                        )
                    else:
                        carb.log_info(f"[ConvertDDS] Converting UDIM tile {tile_path} -> {tile_dds_work}")
                        await run_in_worker_thread(_convert_texture, str(tile_path), str(tile_dds_work), texture_info)
                        await run_in_worker_thread(
                            _write_dds_reuse_metadata,
                            str(tile_dds_work),
                            source_hash,
                        )
                    tile_dds_paths.append(tile_dds_work)
                texture.path = tile_dds_paths[0]
                texture.udim_tiles = tuple(tile_dds_paths)
                continue

            texture_path_str = str(texture.path)
            is_udim = _is_udim_texture(texture_path_str)

            # ---- UDIM path: expand fresh tiles from disk ----
            if is_udim:
                tiles = _get_udim_sequence(texture_path_str)
                if not tiles:
                    raise RuntimeError(f"UDIM texture resolves to no tiles: {texture.path}. UDIM files don't exist.")
                semantic_suffix = get_dds_stem_suffix(texture.texture_type)
                udim_source = texture.original_path or texture.path
                tile_dds_paths = []
                for tile_path_str in tiles:
                    tile_path = pathlib.Path(tile_path_str)
                    if _is_encoded_dds(tile_path, context):
                        tile_dds_paths.append(await self._copy_tile(context, udim_source, tile_path))
                        continue
                    source_hash = await run_in_worker_thread(_hash_existing_file, tile_path_str)
                    texture_info = _get_texture_info(texture.texture_type)
                    tile_dds_work = context.get_work_path(
                        udim_source,
                        stem=tile_path.stem,
                        stem_suffix=semantic_suffix,
                        suffix=DDS_SUFFIX,
                    )
                    tile_dds_final = context.get_output_path(tile_dds_work, source_path=texture.source_path)
                    if await run_in_worker_thread(
                        _can_reuse_dds_output,
                        str(tile_dds_final),
                        source_hash,
                    ):
                        carb.log_info(f"[ConvertDDS] Reusing existing {tile_dds_final}")
                        await run_in_worker_thread(context.copy_to_work_path, tile_dds_final, tile_dds_work)
                        await run_in_worker_thread(
                            _write_dds_reuse_metadata,
                            str(tile_dds_work),
                            source_hash,
                        )
                    else:
                        carb.log_info(f"[ConvertDDS] Converting UDIM tile {tile_path_str} -> {tile_dds_work}")
                        await run_in_worker_thread(_convert_texture, tile_path_str, str(tile_dds_work), texture_info)
                        await run_in_worker_thread(
                            _write_dds_reuse_metadata,
                            str(tile_dds_work),
                            source_hash,
                        )
                    tile_dds_paths.append(tile_dds_work)
                texture.path = tile_dds_paths[0]
                texture.udim_tiles = tuple(tile_dds_paths)
                continue

            # ---- Non-UDIM single-texture path ----
            semantic_suffix = get_dds_stem_suffix(texture.texture_type)
            if _is_encoded_dds(texture.path, context):
                # Already encoded: publish the file unchanged, so it is never compressed twice.
                output_path = context.reserve_output_path(
                    texture.path,
                    source_path=texture.source_path,
                    stem_suffix="",
                    suffix=None,
                )
                texture.path = await run_in_worker_thread(
                    context.copy_to_work_path, texture.path, output_path.work_path
                )
                continue

            old_path = texture.path
            source_hash = await run_in_worker_thread(_hash_existing_file, str(old_path))
            texture_info = _get_texture_info(texture.texture_type)
            output_path = context.reserve_output_path(
                old_path,
                source_path=texture.source_path,
                stem_suffix=semantic_suffix,
                suffix=DDS_SUFFIX,
            )
            new_path = output_path.work_path
            final_path = output_path.output_path
            if await run_in_worker_thread(
                _can_reuse_dds_output,
                str(final_path),
                source_hash,
            ):
                carb.log_info(f"[ConvertDDS] Reusing existing {final_path}")
                texture.path = await run_in_worker_thread(context.copy_to_work_path, final_path, new_path)
                await run_in_worker_thread(
                    _write_dds_reuse_metadata,
                    str(texture.path),
                    source_hash,
                )
                continue

            carb.log_info(f"[ConvertDDS] Converting {old_path} -> {new_path}")
            await run_in_worker_thread(_convert_texture, str(old_path), str(new_path), texture_info)
            await run_in_worker_thread(
                _write_dds_reuse_metadata,
                str(new_path),
                source_hash,
            )

            texture.path = new_path

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
