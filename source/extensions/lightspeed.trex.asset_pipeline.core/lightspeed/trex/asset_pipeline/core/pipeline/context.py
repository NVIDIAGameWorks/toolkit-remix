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

import hashlib
import itertools
import os
import pathlib
import shutil
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from collections.abc import Iterator

import carb
import omni.usd
from omni.flux.asset_pipeline.core import PipelineContext
from pxr import Sdf, Usd

if TYPE_CHECKING:
    from ..jobs.models import TextureLedgerEntry

from .item import RemixAssetItem, TextureAsset


# Keep runner-owned path segments short so a deep workspace root (for example a OneDrive-redirected
# Documents folder) stays under MAX_PATH. No consumer of these paths is given a \\?\ prefix: NVTT
# takes them as narrow C strings (omni.flux.nvtt.core.library), and USD asset resolution, the
# metadata sidecar helpers, and omni.client each resolve them independently.
_WORK_DIR_SOURCE_HASH_LENGTH = 12
_OUTPUT_SOURCE_HASH_LENGTH = 12


def _get_source_path_key(source_path: pathlib.Path) -> str:
    return os.path.normcase(str(source_path.resolve(strict=False)))


@dataclass(frozen=True)
class _IngestionContextLease:
    """One named USD context that is either free or held by one pipeline scope."""

    name: str
    context: omni.usd.UsdContext


# A returned entry is re-leased before a new context is created. The free list therefore grows only
# to the largest number of overlapping pipeline scopes. A context is never destroyed: a queued
# omni.kit.usd.layers event may still reference it, and destroying it then crashes the process.
_INGESTION_CONTEXT_FREE_LIST: list[_IngestionContextLease] = []
_INGESTION_CONTEXT_NAME_COUNTER = itertools.count()


def _lease_ingestion_context() -> _IngestionContextLease:
    """Return one context that no other pipeline scope can lease.

    A free context normally holds no stage. If a previous close failed, the next ``open_stage`` on it
    replaces the leftover stage, the same way the default context replaces the open project.
    """
    if _INGESTION_CONTEXT_FREE_LIST:
        return _INGESTION_CONTEXT_FREE_LIST.pop()

    name = f"remix_asset_pipeline_ingestion_{next(_INGESTION_CONTEXT_NAME_COUNTER)}"
    return _IngestionContextLease(name=name, context=omni.usd.create_context(name))


def _return_ingestion_context(lease: _IngestionContextLease) -> None:
    """Release one context lease so the next scope can reuse it.

    This function never raises. A teardown path calls it while another exception may already be
    propagating.
    """
    if any(free_lease.context is lease.context for free_lease in _INGESTION_CONTEXT_FREE_LIST):
        return
    _INGESTION_CONTEXT_FREE_LIST.append(lease)


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

    A caller must use this context inside ``async with``. The first stage open leases one ingestion
    USD context. The outermost scope exit closes its stage, whether the block finished or raised,
    and returns the lease for reuse. A stage that fails to close stays in the context until the
    next ``open_stage`` on that context replaces it.

    Attributes:
        source_root: Stable project or import root preserved under the output directory.
        work_dir: Runner-owned temporary workspace.
        output_dir: Final local publication directory.
        replace_udim_textures_by_empty: Author an empty asset path for a UDIM texture instead of a
            ``<UDIM>`` pattern. Model ingestion sets this to ``True`` to match the legacy
            ``model_ingestion.json`` schema. Standalone texture optimization leaves it ``False``.
        referenced_layers: Every layer identifier the model composes, recorded by the discovery step.
        texture_ledger: Every texture binding discovered, stored so the prepare job can
            freeze it into :class:`PrepareOptimizationResult`.
        sub_usd_lineage: Every (source_path, published_path) pair for sub-USD layers the runner published
            alongside the model. Populated by the publication step so the mesh job can include them in
            the complete asset lineage.
    """

    source_root: pathlib.Path | None = None
    work_dir: pathlib.Path | None = None
    output_dir: pathlib.Path | None = None
    replace_udim_textures_by_empty: bool = False
    referenced_layers: tuple[str, ...] = ()
    texture_ledger: tuple[TextureLedgerEntry, ...] = ()
    stage_context_name: str = field(default="", init=False)
    _stage_context: omni.usd.UsdContext | None = field(default=None, init=False, repr=False)
    _stage_path: pathlib.Path | None = field(default=None, init=False, repr=False)
    _scope_depth: int = field(default=0, init=False, repr=False)
    _output_paths: dict[pathlib.Path, pathlib.Path] = field(default_factory=dict, init=False, repr=False)
    _used_output_paths: set[pathlib.Path] = field(default_factory=set, init=False, repr=False)
    sub_usd_lineage: list[tuple[pathlib.Path, pathlib.Path]] = field(default_factory=list, init=False, repr=False)

    @property
    def textures(self) -> Iterator[TextureAsset]:
        """Yield every texture record currently owned by the pipeline items."""
        for item in self.items:
            yield from item.textures

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
        stem: str | None = None,
        stem_suffix: str = "",
        suffix: str | None = None,
        create_parent: bool = True,
    ) -> pathlib.Path:
        """Return a runner-owned workspace path for a step output.

        The context owns collision isolation so steps do not hand-roll temp
        filenames. The returned filename stays readable while the parent
        directory is keyed by the absolute source path.

        ``stem`` replaces the source filename stem. A step needs this when the legacy
        output name rewrites part of the stem instead of appending to it.
        """
        work_dir = self._require_work_dir()
        source_key = _get_source_path_key(source_path)
        source_dir = work_dir / hashlib.sha1(source_key.encode("utf-8")).hexdigest()[:_WORK_DIR_SOURCE_HASH_LENGTH]
        if create_parent:
            source_dir.mkdir(parents=True, exist_ok=True)
        output_suffix = source_path.suffix if suffix is None else suffix
        output_stem = source_path.stem if stem is None else stem
        return source_dir / f"{output_stem}{stem_suffix}{output_suffix}"

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

    def clear_output_paths(self) -> None:
        """Clear final output path reservations for a fresh pipeline run."""
        self._output_paths.clear()
        self._used_output_paths.clear()

    def is_in_work_dir(self, path: pathlib.Path) -> bool:
        """Return whether the path already belongs to this pipeline run's workspace."""
        return path.is_relative_to(self._require_work_dir())

    async def __aenter__(self) -> RemixAssetPipelineContext:
        """Open a scope. The first stage open within it leases an ingestion USD context."""
        self._scope_depth += 1
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        """Return the ingestion-context lease when the outermost scope exits."""
        self._scope_depth -= 1
        if self._scope_depth <= 0:
            self._scope_depth = 0
            await self._close_ingestion_context()

    async def open_stage(self, stage_path: pathlib.Path) -> Usd.Stage:
        """Open a USD stage in this scope's leased ingestion context.

        The scope leases the context exclusively, so ingestion never replaces the interactive
        stage in the app's default context. The context holds one stage at a time, so a later call
        with a different path replaces the stage this call returned. A caller must not hold a
        stage, prim, or layer handle across a call with a different path.

        Raises:
            RuntimeError: If the caller is outside an ``async with`` scope, or if the stage cannot
                be opened.
        """
        if self._scope_depth == 0:
            raise RuntimeError('open_stage requires an active "async with RemixAssetPipelineContext(...)" scope')

        context = self._get_stage_context()
        if self._stage_path != stage_path or context.get_stage() is None:
            # Kit currently returns either a bool or a (success, message) tuple here.
            open_result = await context.open_stage_async(str(stage_path))
            open_success = open_result[0] if isinstance(open_result, tuple) else bool(open_result)
            if not open_success:
                raise RuntimeError(f"Unable to open USD stage: {stage_path}")
            self._stage_path = stage_path

        stage = context.get_stage()
        if stage is None:
            raise RuntimeError(f"Unable to get USD stage after opening: {stage_path}")
        return stage

    async def save_stage(self) -> None:
        """Save the stage that is open in the leased ingestion context.

        Raises:
            RuntimeError: If no stage is open in the leased context.
        """
        if self._stage_context is None or self._stage_context.get_stage() is None:
            raise RuntimeError("No USD stage is currently open in the ingestion context")
        await self._stage_context.save_stage_async()

    async def close_stage(self) -> None:
        """Close the open stage and keep the leased ingestion context alive.

        This is the counterpart of ``open_stage``. The context stays alive, so the next
        ``open_stage`` call reuses it. A step that runs one pass for each layer must close between
        rounds, because a context that still holds a layer keeps stale in-memory state after the
        step saves that layer to disk.

        The USD context holds a reference to every layer of the open stage, so this releases the
        root layer before it closes the stage. Layers that stay held break a later stage open in
        the same process.
        """
        stage_context = self._stage_context
        if stage_context is None:
            return

        self._stage_path = None
        stage = stage_context.get_stage()
        if stage is None:
            return
        if not stage_context.can_close_stage():
            return

        # pxr exposes no public API that drops the context's layer references, so the
        # suppression below is unavoidable. The legacy DependencyIterator called the same
        # private helper for this reason before it closed a dependency.
        Sdf._TestTakeOwnership(stage.GetRootLayer())  # noqa: SLF001
        success, error = await stage_context.close_stage_async()
        if not success:
            # The context returns to the pool with its stage; the next open_stage on it replaces that stage.
            carb.log_error(f"Failed to close the stage in ingestion context {self.stage_context_name}: {error}")

    async def _close_ingestion_context(self) -> None:
        """Close the open stage and return this scope's exclusive context lease."""
        stage_context = self._stage_context
        if stage_context is None:
            return

        lease = _IngestionContextLease(name=self.stage_context_name, context=stage_context)
        try:
            await self.close_stage()
        finally:
            self._stage_context = None
            self._stage_path = None
            _return_ingestion_context(lease)

    def _get_stage_context(self) -> omni.usd.UsdContext:
        if self._stage_context is None:
            lease = _lease_ingestion_context()
            self._stage_context = lease.context
            self.stage_context_name = lease.name
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

        Unchanged collector copies use their original filenames. Processed outputs keep their semantic filenames.

        Args:
            work_path: Pipeline workspace file carrying the final semantic filename.
            source_path: Original source used to preserve its project-relative parent hierarchy.

        Returns:
            Relative destination beneath the configured output directory.
        """
        output_name = work_path.name
        resolved_source = source_path.resolve()
        resolved_work = work_path.resolve()
        if any(item.collected_dependencies.get(resolved_source) == resolved_work for item in self.items):
            output_name = source_path.name
        source_root = self.source_root
        if source_root is None:
            return pathlib.Path(output_name)

        try:
            relative_source = resolved_source.relative_to(source_root.resolve(strict=False))
        except ValueError:
            source_hash = hashlib.sha1(_get_source_path_key(source_path).encode("utf-8")).hexdigest()[
                :_OUTPUT_SOURCE_HASH_LENGTH
            ]
            return pathlib.Path("_external") / source_hash / output_name
        return relative_source.with_name(output_name)

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
