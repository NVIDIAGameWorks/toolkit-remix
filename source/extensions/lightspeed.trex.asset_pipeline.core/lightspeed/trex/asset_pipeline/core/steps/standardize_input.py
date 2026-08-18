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

__all__ = ["StandardizeInputStep"]

import pathlib

import carb
from omni.flux.asset_importer.core import ImporterCore
from omni.flux.asset_importer.core.data_models import SUPPORTED_ASSET_EXTENSIONS, SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.asset_importer.core.data_models import UsdExtensions
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep

from ..pipeline_config import RemixAssetPipelineConfig
from ..pipeline_context import RemixAssetPipelineContext
from ..pipeline_item import AssetKind, RemixAssetItem, TextureAsset
from ..worker import run_in_worker_thread


class StandardizeInputStep(PipelineStep):
    """Create the canonical Remix asset item records before processing."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    def __init__(self, config: RemixAssetPipelineConfig):
        """Create the step from immutable pipeline configuration.

        Args:
            config: Pipeline configuration supplying default texture semantics.
        """
        super().__init__()
        self._config = config

    @property
    def name(self) -> str:
        """Return the step identifier.

        Returns:
            Stable pipeline step name.
        """
        return "standardize_input"

    @property
    def description(self) -> str:
        """Return a human-readable description.

        Returns:
            User-facing phase description.
        """
        return "Prepare source files"

    def validate(self, context: PipelineContext) -> list[str]:
        """Validate supported input kinds and file extensions before mutation.

        Args:
            context: Pipeline state to validate.

        Returns:
            Ordered validation errors.
        """
        errors = super().validate(context)
        if errors:
            return errors
        errors.extend(context.validate_work_dir(self.name))
        if errors:
            return errors
        if any(item.kind is AssetKind.MODEL for item in context.items):
            errors.extend(context.validate_output_dir(self.name))

        texture_extensions = {extension.lower() for extension in SUPPORTED_TEXTURE_EXTENSIONS}
        asset_extensions = {extension.lower() for extension in SUPPORTED_ASSET_EXTENSIONS}
        for index, item in enumerate(context.items):
            suffix = item.source_path.suffix.lower()
            if item.kind is AssetKind.TEXTURE and not item.textures and self._config.texture_type is None:
                errors.append(f"{self.name}: item {index} requires an explicit texture type")
            if item.kind is AssetKind.TEXTURE and suffix not in texture_extensions:
                errors.append(f"{self.name}: item {index} has unsupported texture extension '{suffix}'")
            if item.kind is AssetKind.MODEL and suffix not in asset_extensions:
                errors.append(f"{self.name}: item {index} has unsupported model extension '{suffix}'")
        return errors

    def should_run(self, context: RemixAssetPipelineContext) -> bool:
        """Return true when any item still needs canonical records or model import.

        Args:
            context: Remix pipeline state to inspect.

        Returns:
            Whether any source item still needs workspace standardization.
        """
        return any(
            (item.kind is AssetKind.TEXTURE and not item.textures)
            or (
                item.kind is AssetKind.TEXTURE
                and any(not context.is_in_work_dir(texture.path) for texture in item.textures)
            )
            or (
                item.kind is AssetKind.MODEL
                and item.value != self._get_model_work_path(context, item, create_parent=False)
            )
            for item in context.items
        )

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why this step has no work for the already-compatible context.

        Args:
            context: Pipeline state without standardization work.

        Returns:
            User-readable skip reason.
        """
        return "all items are already standardized"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Populate missing texture records and import models into canonical USD files.

        Args:
            context: Pipeline state containing source items and the temporary work directory.

        Raises:
            FileNotFoundError: If a source texture or model does not exist.
            RuntimeError: If model import fails.
            ValueError: If a texture item lacks both a record and configured semantic.
        """
        importer_core: ImporterCore | None = None
        for item in context.items:
            if item.kind is AssetKind.TEXTURE:
                if not item.textures:
                    if self._config.texture_type is None:
                        raise ValueError("Texture items without records require an explicit texture type")
                    item.textures.append(
                        TextureAsset(
                            path=item.source_path,
                            texture_type=self._config.texture_type,
                            original_path=item.source_path,
                        )
                    )
                for texture in item.textures:
                    if texture.original_path is None:
                        texture.original_path = texture.path
                    texture_source_path = texture.path
                    try:
                        texture.path = await run_in_worker_thread(context.copy_to_work_dir, texture_source_path)
                    except FileNotFoundError as exc:
                        raise FileNotFoundError(f"Texture input does not exist: {texture_source_path}") from exc
                continue

            if item.kind is AssetKind.MODEL:
                if importer_core is None:
                    importer_core = ImporterCore()
                await self._standardize_model_item(context, item, importer_core)

    async def _standardize_model_item(
        self,
        context: RemixAssetPipelineContext,
        item: RemixAssetItem,
        importer_core: ImporterCore,
    ) -> None:
        """Import or collect one model source into the configured output directory.

        Args:
            context: Remix pipeline state providing workspace path reservation.
            item: Model item to standardize.
            importer_core: Importer used to convert non-USD model sources.

        Raises:
            FileNotFoundError: If the source model does not exist.
            RuntimeError: If model import fails.
        """
        if not await run_in_worker_thread(item.source_path.exists):
            raise FileNotFoundError(f"Model input does not exist: {item.source_path}")

        work_path = self._get_model_work_path(context, item)
        # Reserve the final model name before any import skip so later texture-reference updates use stable output paths.
        context.get_output_path(work_path, source_path=item.source_path)
        if await run_in_worker_thread(work_path.exists) and item.value == work_path:
            return

        carb.log_info(f"[StandardizeInput] Importing {item.source_path} -> {work_path}")

        success = await importer_core.import_batch_async(
            {
                "data": [
                    {
                        "input_path": str(item.source_path),
                        "output_path": str(work_path),
                        "output_usd_extension": UsdExtensions.USD.value,
                    }
                ]
            }
        )
        if not success:
            raise RuntimeError(f"Failed to import model asset: {item.source_path}")

        item.value = work_path

    def _get_model_work_path(
        self,
        context: RemixAssetPipelineContext,
        item: RemixAssetItem,
        *,
        create_parent: bool = True,
    ) -> pathlib.Path:
        """Return the canonical USD workspace path for one model source.

        Args:
            context: Remix pipeline state providing the workspace directory.
            item: Model item carrying its source path and processing semantic.
            create_parent: Whether to create the workspace parent directory.

        Returns:
            Reserved canonical USD workspace path.
        """
        if item.material_type is None:
            raise ValueError("Model assets require a material semantic")
        return context.get_work_path(
            item.source_path,
            stem_suffix=f".{item.material_type.name.lower()}",
            suffix=f".{UsdExtensions.USD.value}",
            create_parent=create_parent,
        )
