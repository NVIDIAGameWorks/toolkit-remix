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
import subprocess

import carb
import carb.tokens
from lightspeed.common.constants import NVTT_PATH, TEXTURE_INFO
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP, TextureTypes
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from omni.flux.utils.common.path_utils import hash_file, read_metadata, write_metadata

from ..constants import (
    DDS_NVTT_ARGS_METADATA_KEY,
    DDS_SOURCE_HASH_METADATA_KEY,
    DDS_TEXTURE_TYPE_METADATA_KEY,
    NVTT_TIMEOUT_SECONDS,
)
from ..pipeline_context import RemixAssetPipelineContext
from ..pipeline_item import RemixAssetItem, get_texture_source_path, iter_texture_assets
from ..worker import run_in_worker_thread


def _validate_nvtt_args(extra_args: list[str]) -> None:
    """Fail fast when DDS reuse metadata would not round-trip through JSON.

    Args:
        extra_args: NVTT arguments to validate.

    Raises:
        TypeError: If any argument is not a string.
    """
    if not all(isinstance(arg, str) for arg in extra_args):
        raise TypeError(f"NVTT args must be strings for JSON-safe reuse metadata: {extra_args!r}")


def _run_nvtt(
    nvtt_path: str,
    input_path: str,
    output_path: str,
    extra_args: list[str],
    timeout: float = NVTT_TIMEOUT_SECONDS,
) -> None:
    """Run nvtt_export as a subprocess.

    Args:
        nvtt_path: Executable path.
        input_path: Source texture path.
        output_path: Destination DDS path.
        extra_args: Texture-specific NVTT arguments.
        timeout: Maximum conversion duration in seconds.

    Raises:
        subprocess.CalledProcessError: If nvtt_export exits with a non-zero code.
        subprocess.TimeoutExpired: If nvtt_export does not complete within timeout seconds.
    """
    cmd = [nvtt_path, input_path, "--output", output_path] + extra_args
    subprocess.run(cmd, check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout)


def _get_nvtt_args(texture_type: TextureTypes) -> list[str]:
    """Build NVTT arguments for one texture semantic.

    Args:
        texture_type: Texture semantic selecting compression settings.

    Returns:
        Command-line arguments for NVTT.
    """
    input_name = TEXTURE_TYPE_INPUT_MAP[texture_type]
    texture_info = TEXTURE_INFO.get(input_name)
    if texture_info is None:
        # Diffuse is the safest general-purpose encoding for new texture channels that lack explicit NVTT settings.
        carb.log_warn(f"[ConvertDDS] No TEXTURE_INFO for '{input_name}', falling back to DIFFUSE settings")
        texture_info = TEXTURE_INFO[TEXTURE_TYPE_INPUT_MAP[TextureTypes.DIFFUSE]]
    return texture_info.to_nvtt_flag_array()


def _hash_existing_file(path: str) -> str | None:
    """Return a file hash when the path exists locally.

    Args:
        path: Candidate local file path.

    Returns:
        File hash, or ``None`` when the file is absent.
    """
    return hash_file(path) if pathlib.Path(path).exists() else None


def _can_reuse_dds_output(
    path: str,
    source_hash: str | None,
    texture_type: TextureTypes,
    extra_args: list[str],
) -> bool:
    """Return whether an existing DDS was produced from the same conversion inputs.

    Args:
        path: Existing DDS path to inspect.
        source_hash: Hash of the current source texture, if the source exists.
        texture_type: Texture semantic used to select conversion settings.
        extra_args: NVTT arguments required for the current conversion.

    Returns:
        True when the file exists and all recorded conversion inputs match.

    Raises:
        TypeError: If ``extra_args`` cannot be stored safely in JSON metadata.
    """
    _validate_nvtt_args(extra_args)
    if source_hash is None or not pathlib.Path(path).exists():
        return False
    return (
        read_metadata(path, DDS_SOURCE_HASH_METADATA_KEY) == source_hash
        and read_metadata(path, DDS_TEXTURE_TYPE_METADATA_KEY) == texture_type.name
        and read_metadata(path, DDS_NVTT_ARGS_METADATA_KEY) == extra_args
    )


def _write_dds_reuse_metadata(
    path: str,
    source_hash: str | None,
    texture_type: TextureTypes,
    extra_args: list[str],
) -> None:
    """Write the conversion input signature used to validate later DDS reuse.

    Args:
        path: DDS path receiving metadata.
        source_hash: Hash of the source texture, if available.
        texture_type: Texture semantic used for conversion.
        extra_args: NVTT arguments used for conversion.

    Raises:
        TypeError: If ``extra_args`` cannot be stored safely in JSON metadata.
    """
    _validate_nvtt_args(extra_args)
    if source_hash is None:
        return
    write_metadata(path, DDS_SOURCE_HASH_METADATA_KEY, source_hash)
    write_metadata(path, DDS_TEXTURE_TYPE_METADATA_KEY, texture_type.name)
    write_metadata(path, DDS_NVTT_ARGS_METADATA_KEY, extra_args)


class ConvertDDSStep(PipelineStep):
    """Convert texture records to DDS format using nvtt_export."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier.

        Returns:
            Stable pipeline step name.
        """
        return "convert_dds"

    @property
    def description(self) -> str:
        """Return a human-readable description.

        Returns:
            User-facing phase description.
        """
        return "Optimize textures"

    def should_run(self, context: PipelineContext) -> bool:
        """Return true when any texture record still needs a workspace DDS output.

        Args:
            context: Pipeline state to inspect.

        Returns:
            Whether any texture requires conversion or workspace staging.
        """
        for texture in iter_texture_assets(context):
            if texture.path.suffix.lower() != ".dds":
                return True
            if (
                isinstance(context, RemixAssetPipelineContext)
                and context.work_dir
                and not context.is_in_work_dir(texture.path)
            ):
                return True
        return False

    def validate(self, context: PipelineContext) -> list[str]:
        """Validate that the runner provided work and output directories for DDS files.

        Args:
            context: Pipeline state to validate.

        Returns:
            Ordered validation errors.
        """
        errors = super().validate(context)
        if errors:
            return errors
        errors.extend(context.validate_work_dir(self.name))
        errors.extend(context.validate_output_dir(self.name))
        return errors

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why this step has no work for the already-compatible context.

        Args:
            context: Pipeline state without DDS work.

        Returns:
            User-readable skip reason.
        """
        return "all texture records already point to workspace DDS files"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Convert texture records to DDS or reuse an existing DDS output.

        Args:
            context: Pipeline state containing texture records and reserved output paths.

        Raises:
            subprocess.CalledProcessError: If NVTT exits with a non-zero status.
            subprocess.TimeoutExpired: If NVTT exceeds the conversion timeout.
        """
        nvtt_path = carb.tokens.get_tokens_interface().resolve(NVTT_PATH)

        for texture in iter_texture_assets(context):
            semantic_suffix = f".{texture.texture_type.name.lower()}"
            if texture.path.suffix.lower() == ".dds":
                output_path = context.reserve_output_path(
                    texture.path,
                    source_path=get_texture_source_path(texture),
                    stem_suffix=semantic_suffix,
                    suffix=".dds",
                )
                texture.path = await run_in_worker_thread(
                    context.copy_to_work_path, texture.path, output_path.work_path
                )
                continue

            old_path = texture.path
            source_hash = await run_in_worker_thread(_hash_existing_file, str(old_path))
            extra_args = _get_nvtt_args(texture.texture_type)
            output_path = context.reserve_output_path(
                old_path,
                source_path=get_texture_source_path(texture),
                stem_suffix=semantic_suffix,
                suffix=".dds",
            )
            new_path = output_path.work_path
            final_path = output_path.output_path
            if await run_in_worker_thread(
                _can_reuse_dds_output,
                str(final_path),
                source_hash,
                texture.texture_type,
                extra_args,
            ):
                carb.log_info(f"[ConvertDDS] Reusing existing {final_path}")
                texture.path = await run_in_worker_thread(context.copy_to_work_path, final_path, new_path)
                await run_in_worker_thread(
                    _write_dds_reuse_metadata,
                    str(texture.path),
                    source_hash,
                    texture.texture_type,
                    extra_args,
                )
                continue

            carb.log_info(f"[ConvertDDS] Converting {old_path} -> {new_path}")
            await run_in_worker_thread(_run_nvtt, nvtt_path, str(old_path), str(new_path), extra_args)
            await run_in_worker_thread(
                _write_dds_reuse_metadata,
                str(new_path),
                source_hash,
                texture.texture_type,
                extra_args,
            )

            texture.path = new_path
