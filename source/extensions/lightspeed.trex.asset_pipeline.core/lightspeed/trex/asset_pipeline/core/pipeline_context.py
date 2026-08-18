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

__all__ = ["PipelineOutputPath", "RemixAssetPipelineContext"]

import contextlib
import hashlib
import os
import pathlib
import shutil
import uuid
from dataclasses import dataclass, field

import omni.client
import omni.usd
from omni.flux.asset_pipeline.core import PipelineContext
from pxr import Usd

from .pipeline_item import RemixAssetItem


_WORK_DIR_SOURCE_HASH_LENGTH = 20
_OUTPUT_SOURCE_HASH_LENGTH = 12


def _get_source_path_key(source_path: pathlib.Path) -> str:
    return os.path.normcase(str(source_path.resolve(strict=False)))


@dataclass(frozen=True)
class PipelineOutputPath:
    """Runner-owned paths for one publishable pipeline output.

    Steps write ``work_path`` and may inspect ``output_path`` for valid reuse.
    The runner later publishes ``work_path`` to the same ``output_path``.
    """

    work_path: pathlib.Path
    output_path: pathlib.Path


@dataclass
class RemixAssetPipelineContext(PipelineContext[RemixAssetItem]):
    """Typed context for the linear Remix asset processing pipeline.

    Attributes:
        source_root: Stable project or import root preserved under the output directory.
        work_dir: Runner-owned temporary workspace.
        output_dir: Final local publication directory.
    """

    source_root: pathlib.Path | None = None
    work_dir: pathlib.Path | None = None
    output_dir: pathlib.Path | None = None
    stage_context_name: str = field(
        default_factory=lambda: f"remix_asset_pipeline_ingestion_{uuid.uuid4().hex}",
        init=False,
    )
    _stage_context: omni.usd.UsdContext | None = field(default=None, init=False, repr=False)
    _stage_path: pathlib.Path | None = field(default=None, init=False, repr=False)
    _output_paths: dict[pathlib.Path, pathlib.Path] = field(default_factory=dict, init=False, repr=False)
    _used_output_paths: set[pathlib.Path] = field(default_factory=set, init=False, repr=False)

    def __del__(self) -> None:
        try:
            stage_context = self._stage_context
        except AttributeError:
            return
        if stage_context is None:
            return
        with contextlib.suppress(Exception):
            self.close_stage_cache()

    def validate_work_dir(self, step_name: str) -> list[str]:
        """Return validation errors for steps that need runner-owned workspace files."""
        if self.work_dir is None:
            return [f"{step_name}: context.work_dir must be set by the pipeline runner"]
        if not isinstance(self.work_dir, pathlib.Path):
            return [f"{step_name}: context.work_dir must be a pathlib.Path"]
        return []

    def validate_output_dir(self, step_name: str) -> list[str]:
        """Return validation errors for steps that need runner-owned final output paths."""
        if self.output_dir is None:
            return [f"{step_name}: context.output_dir must be set by the pipeline runner"]
        if not isinstance(self.output_dir, pathlib.Path):
            return [f"{step_name}: context.output_dir must be a pathlib.Path"]
        return []

    def get_work_path(
        self,
        source_path: pathlib.Path,
        *,
        stem_suffix: str = "",
        suffix: str | None = None,
        create_parent: bool = True,
    ) -> pathlib.Path:
        """Return a runner-owned workspace path for a step output.

        The context owns collision isolation so steps do not hand-roll temp
        filenames. The returned filename stays readable while the parent
        directory is keyed by the absolute source path.
        """
        work_dir = self._require_work_dir()
        source_key = _get_source_path_key(source_path)
        source_dir = work_dir / hashlib.sha1(source_key.encode("utf-8")).hexdigest()[:_WORK_DIR_SOURCE_HASH_LENGTH]
        if create_parent:
            source_dir.mkdir(parents=True, exist_ok=True)
        output_suffix = source_path.suffix if suffix is None else suffix
        return source_dir / f"{source_path.stem}{stem_suffix}{output_suffix}"

    def copy_to_work_dir(self, path: pathlib.Path) -> pathlib.Path:
        """Copy a source file into this pipeline run's collision-safe workspace."""
        if self.is_in_work_dir(path):
            return path

        work_path = self.get_work_path(path)
        return self.copy_to_work_path(path, work_path)

    def copy_to_work_path(self, path: pathlib.Path, work_path: pathlib.Path) -> pathlib.Path:
        """Copy a source file into an explicit runner-owned workspace path."""
        if not self.is_in_work_dir(work_path):
            raise RuntimeError(f"Workspace output path must belong to this pipeline run: {work_path}")
        work_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, work_path)
        return work_path

    def reserve_output_path(
        self,
        input_path: pathlib.Path,
        *,
        source_path: pathlib.Path | None = None,
        stem_suffix: str = "",
        suffix: str | None = None,
        create_parent: bool = True,
    ) -> PipelineOutputPath:
        """Reserve collision-safe workspace and final paths for one output.

        ``input_path`` controls the readable output filename and source-scoped
        workspace directory. ``source_path`` can provide a stable original input
        for final-name deduplication when ``input_path`` is an intermediate.
        """
        work_path = self.get_work_path(
            input_path,
            stem_suffix=stem_suffix,
            suffix=suffix,
            create_parent=create_parent,
        )
        output_path = self.get_output_path(work_path, source_path=source_path or input_path)
        return PipelineOutputPath(work_path=work_path, output_path=output_path)

    def get_output_path(
        self,
        work_path: pathlib.Path,
        *,
        source_path: pathlib.Path | None = None,
    ) -> pathlib.Path:
        """Return the final collision-safe output path for a workspace file.

        Steps may use this to find reusable outputs from earlier runs. The
        runner uses the same reservation table when publishing final files, so
        steps never need to hand-roll deduplication suffixes.
        """
        output_dir = self._require_output_dir()
        if work_path in self._output_paths:
            return self._output_paths[work_path]

        output_path = output_dir / self._get_relative_output_path(work_path, source_path or work_path)
        if output_path in self._used_output_paths:
            output_path = self._make_unique_output_path(output_path, source_path or work_path)

        self._output_paths[work_path] = output_path
        self._used_output_paths.add(output_path)
        return output_path

    def get_relative_output_asset_path(
        self,
        owner_work_path: pathlib.Path,
        asset_work_path: pathlib.Path,
        *,
        owner_source_path: pathlib.Path | None = None,
        asset_source_path: pathlib.Path | None = None,
    ) -> str:
        """Return a published asset path from one output file to another.

        ``owner_work_path`` is the workspace file that will contain the asset
        reference. ``asset_work_path`` is the workspace file being referenced.
        The context reserves both final names before computing the relative URL
        so steps cannot accidentally author paths to temporary workspace files.
        """
        owner_output_path = self.get_output_path(owner_work_path, source_path=owner_source_path or owner_work_path)
        asset_output_path = self.get_output_path(asset_work_path, source_path=asset_source_path or asset_work_path)
        return omni.client.make_relative_url(str(owner_output_path), str(asset_output_path)).removeprefix("./")

    def clear_output_paths(self) -> None:
        """Clear final output path reservations for a fresh pipeline run."""
        self._output_paths.clear()
        self._used_output_paths.clear()

    def is_in_work_dir(self, path: pathlib.Path) -> bool:
        """Return whether the path already belongs to this pipeline run's workspace."""
        return path.is_relative_to(self._require_work_dir())

    def open_stage(self, stage_path: pathlib.Path) -> Usd.Stage:
        """Open a USD stage in this pipeline run's isolated ingestion context.

        The app may already have a user stage open in the default context. Model
        steps must use this method instead of ``Usd.Stage.Open`` or
        ``omni.usd.get_context()`` so ingestion never replaces the interactive
        stage. The same named context is reused for the whole pipeline run, so
        adjacent model steps do not repeatedly create/destroy USD contexts.
        """
        context = self._get_stage_context()
        if self._stage_path != stage_path or context.get_stage() is None:
            open_result = context.open_stage(str(stage_path))
            # Kit currently returns either a bool or a (success, message) tuple here.
            open_success = open_result[0] if isinstance(open_result, tuple) else bool(open_result)
            if not open_success:
                raise RuntimeError(f"Unable to open USD stage: {stage_path}")
            self._stage_path = stage_path

        stage = context.get_stage()
        if stage is None:
            raise RuntimeError(f"Unable to get USD stage after opening: {stage_path}")
        return stage

    def save_stage(self) -> None:
        """Save the currently cached ingestion stage."""
        if self._stage_context is None or self._stage_context.get_stage() is None:
            raise RuntimeError("No USD stage is currently open in the ingestion context")
        self._stage_context.save_stage()

    def close_stage_cache(self) -> None:
        """Close and destroy this pipeline run's cached ingestion context."""
        stage_context = self._stage_context
        if stage_context is None:
            return

        context_name = self.stage_context_name
        self._stage_context = None
        self._stage_path = None
        self.stage_context_name = f"remix_asset_pipeline_ingestion_{uuid.uuid4().hex}"

        try:
            if stage_context.can_close_stage():
                stage_context.close_stage()
        finally:
            omni.usd.destroy_context(context_name)

    def _get_stage_context(self) -> omni.usd.UsdContext:
        if self._stage_context is None:
            self._stage_context = omni.usd.create_context(self.stage_context_name)
        return self._stage_context

    def _require_work_dir(self) -> pathlib.Path:
        errors = self.validate_work_dir("asset_pipeline_workspace")
        if errors:
            raise RuntimeError(errors[0])
        work_dir = self.work_dir
        if work_dir is None:
            raise RuntimeError("asset_pipeline_workspace: context.work_dir must be set by the pipeline runner")
        return work_dir

    def _require_output_dir(self) -> pathlib.Path:
        errors = self.validate_output_dir("asset_pipeline_output")
        if errors:
            raise RuntimeError(errors[0])
        output_dir = self.output_dir
        if output_dir is None:
            raise RuntimeError("asset_pipeline_output: context.output_dir must be set by the pipeline runner")
        return output_dir

    def _get_relative_output_path(self, work_path: pathlib.Path, source_path: pathlib.Path) -> pathlib.Path:
        """Return one stable source-relative output path.

        Args:
            work_path: Pipeline workspace file carrying the final semantic filename.
            source_path: Original source used to preserve its project-relative parent hierarchy.

        Returns:
            Relative destination beneath the configured output directory.
        """
        source_root = self.source_root
        if source_root is None:
            return pathlib.Path(work_path.name)

        resolved_source = source_path.resolve(strict=False)
        try:
            relative_source = resolved_source.relative_to(source_root.resolve(strict=False))
        except ValueError:
            source_hash = hashlib.sha1(_get_source_path_key(source_path).encode("utf-8")).hexdigest()[
                :_OUTPUT_SOURCE_HASH_LENGTH
            ]
            return pathlib.Path("_external") / source_hash / work_path.name
        return relative_source.with_name(work_path.name)

    def _make_unique_output_path(self, output_path: pathlib.Path, source_path: pathlib.Path) -> pathlib.Path:
        """Return a deterministic suffix fallback for a genuine in-run destination collision.

        Args:
            output_path: Source-relative destination already reserved by another output.
            source_path: Original source used to derive a stable collision suffix.

        Returns:
            Unused destination in the same relative output directory.
        """
        source_hash = hashlib.sha1(_get_source_path_key(source_path).encode("utf-8")).hexdigest()[
            :_OUTPUT_SOURCE_HASH_LENGTH
        ]
        base_stem = output_path.stem
        suffix = output_path.suffix
        output_path = output_path.with_name(f"{base_stem}.{source_hash}{suffix}")
        counter = 2
        while output_path in self._used_output_paths:
            output_path = output_path.with_name(f"{base_stem}.{source_hash}.{counter}{suffix}")
            counter += 1
        return output_path
