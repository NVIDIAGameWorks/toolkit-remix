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

__all__ = ["AssetModifiersCore"]

from collections import defaultdict
from collections.abc import Callable

from lightspeed.common.constants import REMIX_INGESTED_ASSETS_FOLDER
from lightspeed.trex.asset_pipeline.core.jobs.models import ReferenceTarget
from lightspeed.trex.asset_pipeline.core.jobs.asset_replace_apply_target import AssetReplaceApplyTarget
from lightspeed.trex.utils.common.prim_utils import find_prim_with_references, get_prototype
from lightspeed.trex.asset_modifiers.factory import AssetModifierBase
from lightspeed.trex.asset_modifiers.factory import get_instance as _get_asset_modifier_factory
from omni.flux.job_queue.core.job import JobGraph
from omni.flux.utils.common.omni_url import OmniUrl
from omni.kit.app import get_app
from omni.usd import get_context
from pxr import Sdf, Usd

from .constants import FILE_INPUT, SOURCE_INPUT
from .enums import SourceGetter
from .settings import AssetModifierSettings


class AssetModifiersCore:
    """Resolve the active modifier for one USD context and prepare its Job Queue graphs."""

    _NO_MODIFIERS_REASON = "No asset modifiers are installed."

    def __init__(self, context_name: str):
        """Bind the core to a USD context."""
        self._context_name = context_name
        self._settings = AssetModifierSettings()

    @property
    def active_modifier(self) -> type[AssetModifierBase] | None:
        """Return the stored modifier, or the first registered modifier by display name."""
        modifiers = _get_asset_modifier_factory().get_all_plugins()
        active = modifiers.get(self._settings.active_modifier_name)
        return active or min(modifiers.values(), key=lambda modifier: modifier.display_name, default=None)

    def get_selection_block_reason(self, prim: Usd.Prim) -> str | None:
        """Return why a Stage Manager row cannot run the active modifier."""
        modifier = self.active_modifier
        if modifier is None:
            return self._NO_MODIFIERS_REASON
        source = self._settings.get_value(modifier, SOURCE_INPUT)
        if source is not SourceGetter.SELECTED:
            return f"The source is set to {source}. Use Run Modifier in Asset Modifiers."
        if not prim or not modifier().is_compatible(prim):
            return f"'{modifier.display_name}' does not support this prim."
        return None

    def get_run_block_reason(self) -> str | None:
        """Return why Run Modifier cannot start."""
        modifier = self.active_modifier
        if modifier is None:
            return self._NO_MODIFIERS_REASON
        if self._settings.get_value(modifier, SOURCE_INPUT) is SourceGetter.CONSTANT:
            if self._settings.get_value(modifier, FILE_INPUT).is_file():
                return None
            return "Select an existing model file for the source."
        if get_context(self._context_name).get_stage() is None:
            return "Open a project to run an asset modifier."
        return None

    async def prepare_submission(
        self,
        prim_paths: list[str] | None = None,
        progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> tuple[list[JobGraph], dict[str, str]]:
        """Build one graph per source model of the active modifier.

        Args:
            prim_paths: Prims to modify when the source is Selected. None uses the current selection. All and File
                Path Constant sources ignore it.
            progress: Called with the current and total prim count while the prims are read.
            is_cancelled: Polled while the prims are read. A cancelled preparation returns no graphs and no skips.

        Returns:
            The graphs to submit, and the reason for each skipped prim path, or model path for a skipped constant file.

        Raises:
            RuntimeError: If the modifier cannot run. The message is the reason from ``get_run_block_reason()``.
        """
        reason = self.get_run_block_reason()
        if reason:
            raise RuntimeError(reason)
        modifier_type = self.active_modifier
        modifier = modifier_type()
        stage = get_context(self._context_name).get_stage()
        skipped = {}
        # Each model URL keeps its prim paths and reference targets in first-seen order.
        source_paths: defaultdict[str, dict[str, None]] = defaultdict(dict)
        source_targets: defaultdict[str, dict[ReferenceTarget, None]] = defaultdict(dict)
        source = self._settings.get_value(modifier_type, SOURCE_INPUT)
        if source is SourceGetter.CONSTANT:
            source_paths[self._settings.get_value(modifier_type, FILE_INPUT).as_posix()] = {}
        else:
            if source is SourceGetter.ALL:
                prim_paths = [str(prim.GetPath()) for prim in stage.Traverse() if modifier.is_compatible(prim)]
            elif prim_paths is None:
                prim_paths = get_context(self._context_name).get_selection().get_selected_prim_paths()
            layer_stack = stage.GetLayerStack(includeSessionLayers=False)
            for index, path in enumerate(prim_paths, 1):
                if is_cancelled is not None and is_cancelled():
                    return [], {}
                if progress is not None:
                    progress(index, len(prim_paths))
                if index % 50 == 0:
                    await get_app().next_update_async()
                prim = stage.GetPrimAtPath(path)
                if prim:
                    prim = get_prototype(prim) or prim
                if not prim or not modifier.is_compatible(prim):
                    skipped[path] = f"Not supported by {modifier.display_name}."
                    continue
                _owner, references = find_prim_with_references(prim)
                # ponytail: nested model references are skipped until an ancestor-reference search is required.
                targets = [
                    (
                        Sdf.ComputeAssetPathRelativeToLayer(layer, reference.assetPath),
                        ReferenceTarget(str(owner.GetPath()), reference, layer.identifier),
                    )
                    for owner, reference, layer, _index in references
                    if layer in layer_stack and prim.GetPath().HasPrefix(owner.GetPath())
                ]
                if not targets:
                    skipped[path] = "No external model reference composes this prim."
                for source_url, target in targets:
                    source_paths[source_url][str(prim.GetPath())] = None
                    source_targets[source_url][target] = None

        values = {item.name: self._settings.get_value(modifier_type, item) for item in modifier.inputs}
        root_layer = stage.GetRootLayer() if stage is not None else None
        output_directory = None
        if root_layer is not None and not root_layer.anonymous:
            output_directory = OmniUrl(OmniUrl(root_layer.identifier).parent_url) / REMIX_INGESTED_ASSETS_FOLDER
        graphs = []
        for source_url, path_keys in source_paths.items():
            paths = tuple(path_keys)
            job = modifier_type.job_type(
                name=modifier.display_name,
                context_name=self._context_name,
                source_url=source_url,
                prim_paths=paths,
                values=dict(values),
            )
            # Like AI Tools, each job publishes to its own folder, so runs on one source never overwrite each other.
            if output_directory is not None:
                job.output_url = str(output_directory / "modifiers" / modifier.name / str(job.job_id))
            # Stage sources share the reference Replace, Revert, and Undo with ComfyUI. Constant files have no target.
            target = None
            if source_targets[source_url]:
                target = AssetReplaceApplyTarget(
                    context_name=self._context_name,
                    project_path=root_layer.identifier,
                    edit_target_layer=stage.GetEditTarget().GetLayer().identifier,
                    reference_targets=tuple(source_targets[source_url]),
                )
            # Like AI Tools, the graph has the modifier name only, so Job Queue filters stay short.
            graph = JobGraph(name=modifier.display_name)
            graph.add_job(job)
            modifier.build_graph(stage, graph, job, target)
            # Like ComfyUI, a skipped job never enters the queue. Only its reason reaches the user.
            if job.skip_reason is not None:
                skipped |= dict.fromkeys(paths or (source_url,), job.skip_reason)
                continue
            graphs.append(graph)
        return graphs, skipped
