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

__all__ = ["ReferenceStep"]

import pathlib

import carb
import omni.client
import omni.usd
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from omni.flux.utils.common.path_utils import is_absolute_path
from pxr import Sdf, Usd

from ..pipeline.context import RemixAssetPipelineContext
from ..pipeline.item import AssetKind, RemixAssetItem
from ..utils import get_authoring_spec


class ReferenceStep(PipelineStep):
    """Make model asset paths and composition reference arcs relative."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier."""
        return "reference"

    @property
    def description(self) -> str:
        """Return a human-readable description."""
        return "Make asset paths and reference arcs relative"

    def should_run(self, context: PipelineContext) -> bool:
        """Return true when any model item exists."""
        return any(item.kind is AssetKind.MODEL for item in context.items)

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why this step has no work."""
        return "no model items"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Make every model's asset paths and reference arcs relative in place.

        Raises:
            RuntimeError: An absolute path could not be made relative to its layer.
        """
        failing_paths: set[str] = set()
        for item in context.items:
            if item.kind is not AssetKind.MODEL:
                continue

            stage = await context.open_stage(item.value)
            model_parent = item.value.resolve().parent
            changed_layers: dict[str, Sdf.Layer] = {}

            failing = _make_asset_paths_relative(stage, model_parent, changed_layers)
            failing += _make_references_relative(stage, changed_layers)

            for layer in changed_layers.values():
                layer.Save()

            if changed_layers:
                carb.log_info(f"[Reference] Made {len(changed_layers)} layer(s) relative for {item.value}")
            failing_paths.update(failing)

        if failing_paths:
            raise RuntimeError(
                f"Reference step: absolute path(s) could not be made relative: {', '.join(sorted(failing_paths))}"
            )


def _make_asset_paths_relative(
    stage: Usd.Stage,
    model_parent: pathlib.Path,
    changed_layers: dict[str, Sdf.Layer],
) -> list[str]:
    """Rewrite every absolute ``Sdf.ValueTypeNames.Asset`` attribute to a relative path.

    Args:
        stage: Model stage whose attributes are being rewritten.
        model_parent: Directory that owns every layer this step may mutate.
        changed_layers: Layers already edited this run, keyed by identifier; updated in place.

    Returns:
        Prim/attribute paths whose absolute asset path could not be made relative.
    """
    failing: list[str] = []
    predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
    with Sdf.ChangeBlock():
        for prim in Usd.PrimRange(stage.GetPseudoRoot(), predicate):
            for attr in prim.GetAttributes():
                if attr.GetTypeName() != Sdf.ValueTypeNames.Asset or not attr.Get():
                    continue

                attr_path = str(attr.Get().path)
                if not is_absolute_path(attr_path):
                    continue

                resolved_path = attr.Get().resolvedPath

                try:
                    authoring_spec = get_authoring_spec(attr, model_parent)
                except RuntimeError:
                    failing.append(f"{prim.GetPath()}.{attr.GetName()}")
                    continue

                rel_path = omni.client.make_relative_url(authoring_spec.layer.identifier, resolved_path)
                if rel_path == resolved_path:
                    failing.append(f"{prim.GetPath()}.{attr.GetName()}")
                    continue

                authoring_spec.default = Sdf.AssetPath(rel_path)
                changed_layers[authoring_spec.layer.identifier] = authoring_spec.layer

    return failing


def _make_references_relative(stage: Usd.Stage, changed_layers: dict[str, Sdf.Layer]) -> list[str]:
    """Flatten and rewrite every absolute reference arc to a relative path.

    A weaker-layer reference is flattened into one explicit reference list on the
    stage edit target, dropping any authored layer offset -- this replicates a
    known bug in the validator plugin this step replaces. A reference already on
    the edit target is fixed in place. A reference on a stronger layer cannot be
    edited from here.

    Args:
        stage: Model stage whose reference arcs are being rewritten.
        changed_layers: Layers already edited this run, keyed by identifier; updated in place.

    Returns:
        Prim paths with an absolute reference above the stage edit target.
    """
    cur_layer = stage.GetEditTarget().GetLayer()
    base_path = cur_layer.identifier
    # GetUsedLayers() is not strength-ordered, so strength is read from the stage's own local
    # layer stack (session, root, sublayers, strongest first) instead. Any authoring layer ahead
    # of cur_layer there -- only ever the session layer in practice -- is stronger and unfixable.
    local_stack = list(stage.GetLayerStack(includeSessionLayers=True))
    stronger_layers = set(local_stack[: local_stack.index(cur_layer)])

    failing: list[str] = []
    predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
    with Sdf.ChangeBlock():
        for prim in Usd.PrimRange(stage.GetPseudoRoot(), predicate):
            refs_and_layers = omni.usd.get_composed_references_from_prim(prim)
            if not refs_and_layers:
                continue

            abs_in_current_layer = False
            abs_in_weaker_layer = False
            unfixable = False
            for ref, ref_layer in refs_and_layers:
                if not is_absolute_path(str(ref.assetPath)):
                    continue
                if ref_layer == cur_layer:
                    abs_in_current_layer = True
                elif ref_layer in stronger_layers:
                    unfixable = True
                else:
                    abs_in_weaker_layer = True

            if abs_in_weaker_layer:
                flattened = [
                    Sdf.Reference(
                        assetPath=omni.client.make_relative_url(
                            base_path, Sdf.ComputeAssetPathRelativeToLayer(ref_layer, ref.assetPath)
                        ),
                        primPath=ref.primPath,
                        customData=ref.customData,
                    )
                    for ref, ref_layer in refs_and_layers
                    if ref_layer not in stronger_layers
                ]
                prim.GetReferences().SetReferences(flattened)
                changed_layers[cur_layer.identifier] = cur_layer
            elif abs_in_current_layer:
                for prim_spec in prim.GetPrimStack():
                    if prim_spec.layer != cur_layer:
                        continue
                    op = prim_spec.GetInfo(Sdf.PrimSpec.ReferencesKey)
                    if op.isExplicit:
                        op.explicitItems = _make_refs_relative(cur_layer, op.explicitItems)
                    else:
                        op.addedItems = _make_refs_relative(cur_layer, op.addedItems)
                        op.prependedItems = _make_refs_relative(cur_layer, op.prependedItems)
                        op.appendedItems = _make_refs_relative(cur_layer, op.appendedItems)
                        op.deletedItems = _make_refs_relative(cur_layer, op.deletedItems)
                        op.orderedItems = _make_refs_relative(cur_layer, op.orderedItems)
                    prim_spec.SetInfo(Sdf.PrimSpec.ReferencesKey, op)
                    changed_layers[cur_layer.identifier] = cur_layer
                    break

            if unfixable:
                failing.append(str(prim.GetPath()))

    return failing


def _make_refs_relative(layer: Sdf.Layer, refs: list[Sdf.Reference]) -> list[Sdf.Reference]:
    """Return ``refs`` with every absolute asset path rewritten relative to ``layer``.

    Args:
        layer: Layer the rewritten references will be authored into.
        refs: Reference items to inspect and rewrite.

    Returns:
        Equivalent references with absolute asset paths made relative.
    """
    result = []
    for ref in refs:
        if is_absolute_path(str(ref.assetPath)):
            ref_new = Sdf.Reference(
                assetPath=omni.client.make_relative_url(layer.identifier, str(ref.assetPath)),
                primPath=ref.primPath,
                layerOffset=ref.layerOffset,
                customData=ref.customData,
            )
        else:
            ref_new = ref
        result.append(ref_new)
    return result
