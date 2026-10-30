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

__all__ = [
    "APPLIED",
    "ORIGINAL",
    "apply_atomically",
    "apply_references",
    "asset_metadata_paths",
    "check_apply_stage",
    "get_apply_stage",
    "get_block_reason",
    "raise_external_edit",
    "reference_state",
    "revert_atomically",
    "revert_references",
]

from collections.abc import Callable
from hashlib import sha256
from typing import TYPE_CHECKING

import omni.client
import omni.kit.commands
import omni.kit.undo
import omni.usd
from lightspeed.common import constants
from lightspeed.trex.asset_replacements.core.shared import Setup
from omni.flux.job_queue.core.errors import ApplyExecutionError
from omni.usd import get_context
from pxr import Sdf, Usd

from ..metadata import (
    MetadataApplyReceipt,
    capture_metadata_receipt,
    get_current_validation_extensions,
    revert_metadata,
    write_metadata_for_paths,
)
from ..worker import run_in_worker_thread
from .apply_stage_watcher import get_apply_stage_watcher
from .models import MeshOptimizationResult, ReferenceTarget

if TYPE_CHECKING:
    from .apply_stage_target import ApplyStageTarget


ORIGINAL = "original"
APPLIED = "applied"
# Reapply removes only the source child that this job restored.
_RESTORED_BY_ATTR = "remix_restored_by"
# The owner and output URL distinguish jobs and detect external reference edits.
_GENERATED_FOR_ATTR = "remix_generated_for"


def _generated_marker(owner_prim_path: str, asset_url: str) -> str:
    """Return the ``_GENERATED_FOR_ATTR`` value for one owner and one job's generated asset."""
    return f"{owner_prim_path} {_normalize_url(asset_url)}"


def _in_place_marker_attr(asset_url: str) -> str:
    """Return a separate marker attribute for each generated asset on one owner."""
    return f"{_GENERATED_FOR_ATTR}:asset_{sha256(_normalize_url(asset_url).encode()).hexdigest()}"


def get_apply_stage(target: ApplyStageTarget) -> tuple[Usd.Stage, Sdf.Layer]:
    """Resolve the live stage only when it matches the submitted Apply target.

    Args:
        target: Persisted project and edit-layer identity.

    Returns:
        Matching live stage and edit layer.

    Raises:
        ApplyExecutionError: If the submitted project or edit layer is unavailable.
    """
    stage = get_context(target.context_name).get_stage()
    if stage is None:
        raise ApplyExecutionError(
            "Open the project used to create this job before applying its outputs.",
            RuntimeError("No USD stage is open for this job"),
        )
    opened_project = str(stage.GetRootLayer().identifier)
    if opened_project != target.project_path:
        raise ApplyExecutionError(
            "This job belongs to a different project. Open the project used to create it before applying its outputs.\n"
            f"Job project: {target.project_path}\nOpened project: {opened_project}",
            RuntimeError("The open project differs from the project used to submit this job"),
        )
    target_layer = next(
        (
            layer
            for layer in stage.GetLayerStack(includeSessionLayers=False)
            if str(layer.identifier) == target.edit_target_layer
        ),
        None,
    )
    if target_layer is None:
        raise ApplyExecutionError(
            "The edit layer used to create this job is unavailable. Restore that layer before applying its outputs.",
            RuntimeError("The target layer used to submit this job is no longer in the open project"),
        )
    return stage, target_layer


def asset_metadata_paths(value: MeshOptimizationResult) -> list[str]:
    """Return unique output URLs for the mesh and its textures."""
    return list(dict.fromkeys((value.asset_url, *(item.asset_url for item in value.texture_result.items))))


async def _write_output_metadata(paths: list[str], validation_passed: bool) -> None:
    """Write deterministic metadata to all outputs.

    Args:
        paths: Local or remote output files to annotate.
        validation_passed: Combined pipeline validation result.
    """
    validation_extensions = get_current_validation_extensions()
    await run_in_worker_thread(write_metadata_for_paths, paths, validation_extensions, validation_passed)


def raise_external_edit() -> None:
    """Raise the external-edit conflict for an Apply target.

    Raises:
        ApplyExecutionError: The current target differs from the durable receipt.
    """
    raise ApplyExecutionError(
        "An Apply target changed outside this job. Review the project changes and try again.",
        RuntimeError("An Apply target differs from its durable receipt. No changes occurred"),
    )


def check_apply_stage(target: ApplyStageTarget, stage: Usd.Stage, target_layer: Sdf.Layer) -> None:
    """Reject a stage or edit layer change after a sidecar await."""
    try:
        current_stage, current_layer = get_apply_stage(target)
    except ApplyExecutionError:
        raise_external_edit()
    if current_stage is not stage or current_layer is not target_layer:
        raise_external_edit()


def _normalize_url(url: str) -> str:
    """Return one comparable spelling of an asset URL."""
    return omni.client.normalize_url(url).replace("\\", "/")


def _layer_index(stage: Usd.Stage) -> dict[str, Sdf.Layer]:
    """Return the project layer stack keyed by identifier, built once per operation."""
    return {str(layer.identifier): layer for layer in stage.GetLayerStack(includeSessionLayers=False)}


def _find_source_reference(
    prim: Usd.Prim,
    layers: dict[str, Sdf.Layer],
    reference_target: ReferenceTarget,
    source_index: dict[str, dict[tuple[str, str], list[tuple[Sdf.Reference, Sdf.Layer]]]] | None = None,
) -> tuple[Sdf.Reference, Sdf.Layer] | None:
    """Find the captured source among a prim's current composed references."""
    source = reference_target.source_reference
    source_url = _normalize_url(
        Sdf.ComputeAssetPathRelativeToLayer(
            _find_layer(layers, reference_target.source_layer_identifier), source.assetPath
        )
    )
    if source_index is None:
        source_index = {}
    prim_path = str(prim.GetPath())
    if prim_path not in source_index:
        references = {}
        for reference, layer in omni.usd.get_composed_references_from_prim(prim):
            key = (
                _normalize_url(Sdf.ComputeAssetPathRelativeToLayer(layer, reference.assetPath)),
                str(reference.primPath),
            )
            references.setdefault(key, []).append((reference, layer))
        source_index[prim_path] = references
    for reference, layer in source_index[prim_path].get((source_url, str(source.primPath)), ()):
        if reference.layerOffset == source.layerOffset and reference.customData == source.customData:
            return reference, layer
    return None


def _owner_prim(stage: Usd.Stage, owner_prim_path: str) -> Usd.Prim:
    """Return one captured owner prim.

    Raises:
        ApplyExecutionError: The owner no longer exists.
    """
    owner = stage.GetPrimAtPath(owner_prim_path)
    if not owner.IsValid():
        raise_external_edit()
    return owner


def _replaces_in_place(stage: Usd.Stage, reference_target: ReferenceTarget, *, replace: bool) -> bool:
    """Return whether Replace swaps the source on the Remix reference owner itself.

    Raises:
        ApplyExecutionError: The owner no longer exists.
    """
    return (
        replace
        and reference_target.source_reference is not None
        and _owner_prim(stage, reference_target.owner_prim_path).GetAttribute(constants.IS_REMIX_REF_ATTR).Get() is True
    )


def _relative_reference(target_layer: Sdf.Layer, asset_url: str, source: Sdf.Reference | None = None) -> Sdf.Reference:
    """Return one reference to an absolute asset URL, spelled relative to the target layer like ``Setup`` does.

    Args:
        target_layer: Layer that will author the reference.
        asset_url: Absolute asset URL to reference.
        source: Reference whose primPath, layerOffset, and customData to keep. None references the default prim.
    """
    asset_path = omni.client.normalize_url(omni.client.make_relative_url(target_layer.identifier, asset_url))
    asset_path = asset_path.replace("\\", "/")
    if source is None:
        return Sdf.Reference(asset_path)
    return Sdf.Reference(asset_path, source.primPath, source.layerOffset, source.customData)


def _find_generated_reference(prim: Usd.Prim, asset_url: str) -> tuple[Sdf.Reference, Sdf.Layer] | None:
    """Find the generated default-prim reference among a prim's composed references."""
    expected = _normalize_url(asset_url)
    for reference, layer in omni.usd.get_composed_references_from_prim(prim):
        if (
            reference.primPath == Sdf.Path.emptyPath
            and reference.layerOffset == Sdf.LayerOffset()
            and not reference.customData
            and _normalize_url(Sdf.ComputeAssetPathRelativeToLayer(layer, reference.assetPath)) == expected
        ):
            return reference, layer
    return None


def _in_place_state(
    stage: Usd.Stage,
    layers: dict[str, Sdf.Layer],
    reference_target: ReferenceTarget,
    asset_url: str,
    source_index: dict[str, dict[tuple[str, str], list[tuple[Sdf.Reference, Sdf.Layer]]]] | None = None,
) -> str:
    """Classify one Remix reference owner that Replace swaps in place.

    Applied: the owner carries this job's ``_GENERATED_FOR_ATTR`` marker, composes the generated model, and no
    longer composes the source. Original: the owner composes the source, not the generated model, and does not
    carry this job's marker.

    Raises:
        ApplyExecutionError: The owner is missing or in any other state.
    """
    owner = _owner_prim(stage, reference_target.owner_prim_path)
    marker = _generated_marker(reference_target.owner_prim_path, asset_url)
    marked = any(
        owner.GetAttribute(attr_name).Get() == marker
        for attr_name in (_in_place_marker_attr(asset_url), _GENERATED_FOR_ATTR)
    )
    source = _find_source_reference(owner, layers, reference_target, source_index) is not None
    generated = _find_generated_reference(owner, asset_url) is not None
    if marked and generated and not source:
        return APPLIED
    if not marked and source and not generated:
        return ORIGINAL
    raise_external_edit()
    return None


def _generated_anchor(stage: Usd.Stage, owner_prim_path: str) -> tuple[Usd.Prim, Usd.Prim]:
    """Return the owner prim and the prim under which ``Setup`` creates its Remix reference children.

    ``Setup.add_new_reference`` creates the child under the owner, except when the owner is itself a Remix
    reference child: then it creates a sibling under the owner's parent. Replace on a Remix reference owner
    creates no child at all; it swaps the reference on the owner (see ``_in_place_state``).

    Raises:
        ApplyExecutionError: The owner no longer exists.
    """
    owner = _owner_prim(stage, owner_prim_path)
    anchor = owner.GetParent() if owner.GetAttribute(constants.IS_REMIX_REF_ATTR).Get() is True else owner
    return owner, anchor


def _generated_children(
    stage: Usd.Stage,
    owner_prim_path: str,
    asset_url: str,
    children_by_anchor: dict[str, dict[str, list[Usd.Prim]]],
) -> list[Usd.Prim]:
    """Return the Remix reference children that this job's Apply created for one owner.

    Args:
        stage: Live stage.
        owner_prim_path: Reference owner captured at submission.
        asset_url: Optimized asset URL that Apply references.
        children_by_anchor: Generated children indexed once per anchor for this classification.

    Returns:
        Generated children in stage order. Empty when Apply created none for this owner.

    Raises:
        ApplyExecutionError: The owner no longer exists, or a generated child no longer composes exactly the
            generated asset (its reference was changed outside this job).
    """
    expected = _normalize_url(asset_url)
    marker = _generated_marker(owner_prim_path, asset_url)
    _owner, anchor = _generated_anchor(stage, owner_prim_path)
    anchor_path = str(anchor.GetPath())
    if anchor_path not in children_by_anchor:
        indexed_children: dict[str, list[Usd.Prim]] = {}
        for child in anchor.GetChildren():
            child_marker = child.GetAttribute(_GENERATED_FOR_ATTR).Get()
            if child_marker:
                indexed_children.setdefault(child_marker, []).append(child)
        children_by_anchor[anchor_path] = indexed_children
    children = []
    for child in children_by_anchor[anchor_path].get(marker, ()):
        if [
            (
                _normalize_url(Sdf.ComputeAssetPathRelativeToLayer(layer, reference.assetPath)),
                reference.primPath,
                reference.layerOffset,
                reference.customData,
            )
            for reference, layer in omni.usd.get_composed_references_from_prim(child)
        ] != [(expected, Sdf.Path.emptyPath, Sdf.LayerOffset(), {})]:
            raise_external_edit()
        children.append(child)
    return children


def _restored_source_children(
    stage: Usd.Stage,
    layers: dict[str, Sdf.Layer],
    reference_target: ReferenceTarget,
    asset_url: str,
) -> list[str]:
    """Return the Remix reference children that this job's Revert authored to compose one removed source.

    Args:
        stage: Live stage.
        layers: Project layer stack by identifier.
        reference_target: Owner and captured source reference.
        asset_url: Optimized asset URL of this job, written by Revert as the restore marker.

    Returns:
        Child paths in stage order. Empty when the target has no source, the owner is itself a Remix reference
        (Revert puts the source back on the owner), or no Revert of this job restored it. A source child the
        user authored, or another job restored, never matches.
    """
    if reference_target.source_reference is None:
        return []
    owner, anchor = _generated_anchor(stage, reference_target.owner_prim_path)
    if anchor != owner:
        return []
    expected = _normalize_url(asset_url)
    return [
        str(child.GetPath())
        for child in owner.GetChildren()
        if child.GetAttribute(constants.IS_REMIX_REF_ATTR).Get()
        and child.GetAttribute(_RESTORED_BY_ATTR).Get() == expected
        and _find_source_reference(child, layers, reference_target) is not None
        and len(omni.usd.get_composed_references_from_prim(child)) == 1
    ]


def _source_composed(
    stage: Usd.Stage,
    layers: dict[str, Sdf.Layer],
    reference_target: ReferenceTarget,
    source_index: dict[str, dict[tuple[str, str], list[tuple[Sdf.Reference, Sdf.Layer]]]],
    restored_source_index: dict[str, dict[tuple[str, str], list[tuple[Sdf.Reference, Sdf.Layer]]]],
) -> bool:
    """Return whether one owner still composes its source: on itself, or on a Remix reference child a Revert restored."""
    owner = stage.GetPrimAtPath(reference_target.owner_prim_path)
    if _find_source_reference(owner, layers, reference_target, source_index) is not None:
        return True
    owner_path = reference_target.owner_prim_path
    if owner_path not in restored_source_index:
        references = {}
        for child in owner.GetChildren():
            if not child.GetAttribute(constants.IS_REMIX_REF_ATTR).Get():
                continue
            for reference, layer in omni.usd.get_composed_references_from_prim(child):
                key = (
                    _normalize_url(Sdf.ComputeAssetPathRelativeToLayer(layer, reference.assetPath)),
                    str(reference.primPath),
                )
                references.setdefault(key, []).append((reference, layer))
        restored_source_index[owner_path] = references
    return _find_source_reference(owner, layers, reference_target, restored_source_index) is not None


def reference_state(
    stage: Usd.Stage,
    reference_targets: tuple[ReferenceTarget, ...],
    asset_url: str,
    *,
    replace: bool,
) -> tuple[str | None, dict[str, list[Usd.Prim]]]:
    """Classify every owner against the reference change Apply makes.

    A Remix reference owner that Replace swaps in place is classified by ``_in_place_state``. Every other owner is
    classified by the generated children Apply creates.

    Args:
        stage: Live stage.
        reference_targets: Captured reference owners.
        asset_url: Optimized asset URL that Apply references.
        replace: Whether Apply replaces sources instead of appending references.

    Returns:
        The shared owner state and the generated children by owner path. The state is ``None`` when
        the target changes no reference.

    Raises:
        ApplyExecutionError: An owner is missing, owners disagree, an owner has more children than Apply
            created, a generated child was changed, an applied Replace owner still composes its source, or an
            original Replace owner no longer composes its source.
    """
    if not reference_targets:
        return None, {}
    layers = _layer_index(stage)
    states: set[str] = set()
    source_index: dict[str, dict[tuple[str, str], list[tuple[Sdf.Reference, Sdf.Layer]]]] = {}
    restored_source_index: dict[str, dict[tuple[str, str], list[tuple[Sdf.Reference, Sdf.Layer]]]] = {}
    expected_counts: dict[str, int] = {}
    replace_sources: list[ReferenceTarget] = []
    for reference_target in reference_targets:
        if _replaces_in_place(stage, reference_target, replace=replace):
            states.add(_in_place_state(stage, layers, reference_target, asset_url, source_index))
            continue
        if replace:
            expected_counts[reference_target.owner_prim_path] = 1
            if reference_target.source_reference is not None:
                replace_sources.append(reference_target)
        else:
            expected_counts[reference_target.owner_prim_path] = (
                expected_counts.get(reference_target.owner_prim_path, 0) + 1
            )
    children: dict[str, list[Usd.Prim]] = {}
    if expected_counts:
        children_by_anchor: dict[str, dict[str, list[Usd.Prim]]] = {}
        children = {
            owner: _generated_children(stage, owner, asset_url, children_by_anchor) for owner in expected_counts
        }
        if all(not found for found in children.values()):
            # A removed generated child without its source is an external edit.
            if not all(
                _source_composed(stage, layers, reference_target, source_index, restored_source_index)
                for reference_target in replace_sources
            ):
                raise_external_edit()
            states.add(ORIGINAL)
            children = {}
        elif all(len(children[owner]) == count for owner, count in expected_counts.items()):
            if any(
                _source_composed(stage, layers, reference_target, source_index, restored_source_index)
                for reference_target in replace_sources
            ):
                raise_external_edit()
            states.add(APPLIED)
        else:
            raise_external_edit()
    if len(states) != 1:
        raise_external_edit()
    return states.pop(), children


def _run_undoable(action: Callable[[], None]) -> None:
    """Run stage mutations in one undo group and undo that group when the action fails.

    Args:
        action: Synchronous stage mutations.

    Raises:
        Exception: The original failure, after the partial group was undone.
    """
    depth = len(omni.kit.undo.get_undo_stack())
    try:
        with omni.kit.undo.group(remove_if_empty=True):
            action()
    except Exception:
        if len(omni.kit.undo.get_undo_stack()) > depth:
            omni.kit.undo.undo()
        raise


def _find_layer(layers: dict[str, Sdf.Layer], identifier: str) -> Sdf.Layer:
    """Return the project layer with one exact identifier.

    Raises:
        ApplyExecutionError: The layer is not in the project layer stack.
    """
    layer = layers.get(identifier)
    if layer is None:
        raise ApplyExecutionError(
            "A source layer used by this job is no longer available. Restore it before applying the asset.",
            RuntimeError("A captured source reference layer is not in the project layer stack"),
        )
    return layer


def _mark_child(prim: Usd.Prim, attr_name: str, value: str) -> None:
    """Author one string marker attribute on a Remix reference prim inside the current undo group."""
    omni.kit.commands.execute(
        "CreateUsdAttribute", prim=prim, attr_name=attr_name, attr_type=Sdf.ValueTypeNames.String, attr_value=value
    )


def _replace_reference_in_place(
    stage: Usd.Stage,
    setup: Setup,
    owner: Usd.Prim,
    source: Sdf.Reference,
    source_layer: Sdf.Layer,
    replacement: Sdf.Reference,
) -> None:
    """Replace one reference without changing its composition strength."""
    references = omni.usd.get_composed_references_from_prim(owner)
    index = references.index((source, source_layer))
    setup.remove_selected_reference(stage, owner.GetPath(), source, source_layer)
    references = list(stage.GetEditTarget().GetLayer().GetPrimAtPath(owner.GetPath()).referenceList.explicitItems)
    references.insert(index, replacement)
    omni.kit.commands.execute(
        "SetExplicitReferencesCommand",
        stage=stage,
        prim_path=str(owner.GetPath()),
        reference=replacement,
        to_set=references,
    )


def _revert_in_place(
    stage: Usd.Stage,
    setup: Setup,
    layers: dict[str, Sdf.Layer],
    reference_target: ReferenceTarget,
    asset_url: str,
    target_layer: Sdf.Layer,
) -> None:
    """Swap the generated reference back to the captured source on a Remix reference owner and clear its marker.

    The source returns with its captured primPath, layerOffset, and customData, spelled relative to the target
    layer. Nothing is deleted. The edit target must already be ``target_layer``.
    """
    owner = _owner_prim(stage, reference_target.owner_prim_path)
    generated = _find_generated_reference(owner, asset_url)
    source = reference_target.source_reference
    source_layer = _find_layer(layers, reference_target.source_layer_identifier)
    if generated is not None:
        _replace_reference_in_place(
            stage,
            setup,
            owner,
            *generated,
            _relative_reference(
                target_layer, Sdf.ComputeAssetPathRelativeToLayer(source_layer, source.assetPath), source
            ),
        )
    else:
        omni.kit.commands.execute(
            "AddReference",
            stage=stage,
            prim_path=owner.GetPath(),
            reference=_relative_reference(
                target_layer, Sdf.ComputeAssetPathRelativeToLayer(source_layer, source.assetPath), source
            ),
        )
    omni.kit.commands.execute(
        "RemoveProperty",
        prop_path=owner.GetPath().AppendProperty(
            _in_place_marker_attr(asset_url)
            if owner.HasAttribute(_in_place_marker_attr(asset_url))
            else _GENERATED_FOR_ATTR
        ),
        usd_context_name=stage,
        remove_from_layers=[target_layer],
    )


def get_block_reason(target: ApplyStageTarget) -> str | None:
    """Return why the submitted stage cannot accept an Apply operation.

    The target's context is watched from here on, so opening or closing its project refreshes this reason.
    """
    get_apply_stage_watcher().watch(target.context_name)
    try:
        get_apply_stage(target)
    except ApplyExecutionError as error:
        return error.reason
    return None


async def apply_atomically(
    metadata_paths: list[str],
    validation_passed: bool,
    classify: Callable[[], str | None],
    mutate: Callable[[], None],
    failure_message: str,
    check_stage: Callable[[], None],
) -> None:
    """Write sidecars, re-check the target after the await, then mutate the stage once in one undo group.

    Args:
        metadata_paths: Output files whose sidecars Apply writes.
        validation_passed: Combined pipeline validation result.
        classify: Returns the live target state. Called before and after the sidecar await.
        mutate: Synchronous stage mutations for an original target.
        failure_message: User-facing message if Apply fails.
        check_stage: Rejects a stage or edit layer change after the sidecar await.

    Raises:
        ApplyExecutionError: The target changed outside this job, or Apply failed and was rolled back.
        BaseException: Cancellation and other non-Exception failures, after the sidecar rollback.
    """
    state = classify()
    metadata_rollback = await run_in_worker_thread(capture_metadata_receipt, metadata_paths)
    try:
        await _write_output_metadata(metadata_paths, validation_passed)
        check_stage()
        if classify() != state:
            raise_external_edit()
        if state == ORIGINAL:
            _run_undoable(mutate)
    except BaseException as error:
        await run_in_worker_thread(revert_metadata, metadata_rollback)
        if not isinstance(error, Exception) or isinstance(error, ApplyExecutionError):
            raise
        raise ApplyExecutionError(failure_message, error) from error


async def revert_atomically(
    metadata_paths: list[str],
    receipt: MetadataApplyReceipt,
    classify: Callable[[], str | None],
    restore: Callable[[], None],
    failure_message: str,
    check_stage: Callable[[], None],
) -> None:
    """Restore sidecars inside the recovery boundary, re-check the target, then the stage in one undo group.

    Args:
        metadata_paths: Output files whose sidecars Revert restores.
        receipt: Durable metadata receipt from the first Apply.
        classify: Returns the live target state. Called before and after the sidecar await.
        restore: Synchronous stage restore for an applied target.
        failure_message: User-facing message if the stage restore fails.
        check_stage: Rejects a stage or edit layer change after the sidecar await.

    Raises:
        ApplyExecutionError: The target changed outside this job, or the stage restore failed. Sidecars are restored.
        BaseException: Cancellation and other non-Exception failures, after the sidecar restore.
    """
    state = classify()
    metadata_rollback = await run_in_worker_thread(capture_metadata_receipt, metadata_paths)
    try:
        # A later failure must restore the sidecars from before this attempt.
        await run_in_worker_thread(revert_metadata, receipt)
        check_stage()
        if classify() != state:
            raise_external_edit()
        if state == APPLIED:
            _run_undoable(restore)
    except BaseException as error:
        await run_in_worker_thread(revert_metadata, metadata_rollback)
        if not isinstance(error, Exception) or isinstance(error, ApplyExecutionError):
            raise
        raise ApplyExecutionError(failure_message, error) from error


def apply_references(
    stage: Usd.Stage,
    setup: Setup,
    target_layer: Sdf.Layer,
    reference_targets: tuple[ReferenceTarget, ...],
    asset_url: str,
    *,
    context_name: str,
    replace: bool,
) -> None:
    """Add or replace model references on the current edit target."""
    layers = _layer_index(stage)
    last_references = {reference.owner_prim_path: reference for reference in reference_targets}
    for reference_target in reference_targets:
        owner_path = Sdf.Path(reference_target.owner_prim_path)
        if replace and reference_target.source_reference is not None:
            owner = stage.GetPrimAtPath(owner_path)
            # Reference commands reserve only the reference field, not newly created owner specs.
            if target_layer.GetPrimAtPath(owner_path) is None:
                omni.kit.commands.execute("CreateReferenceOwnerSpecCommand", layer=target_layer, prim_path=owner_path)
            # A previous Revert restored the source as a child. Replace must remove that child before reapply.
            restored = _restored_source_children(stage, layers, reference_target, asset_url)
            if restored:
                omni.kit.commands.execute("DeletePrims", paths=restored, context_name=context_name)
            source, source_layer = _find_source_reference(owner, layers, reference_target) or (
                reference_target.source_reference,
                _find_layer(layers, reference_target.source_layer_identifier),
            )
            # Remove every selected source before creating one generated child for this owner.
            if reference_target != last_references[reference_target.owner_prim_path]:
                setup.remove_selected_reference(stage, owner_path, source, source_layer)
                continue
            if owner.GetAttribute(constants.IS_REMIX_REF_ATTR).Get() is True:
                # Replace keeps the owner path and other references. It creates no sibling.
                _replace_reference_in_place(
                    stage,
                    setup,
                    owner,
                    source,
                    source_layer,
                    _relative_reference(target_layer, asset_url),
                )
                child_path = owner_path
            else:
                _added, child_path = setup.replace_reference(
                    stage,
                    owner_path,
                    source,
                    source_layer,
                    asset_url,
                    target_layer,
                    preserve_other_references=True,
                    use_undo_group=False,
                )
        else:
            _added, child_path = setup.add_new_reference(
                stage,
                owner_path,
                asset_url,
                Setup.get_ref_default_prim_tag(),
                target_layer,
            )
        _mark_child(
            stage.GetPrimAtPath(child_path),
            _in_place_marker_attr(asset_url) if child_path == owner_path else _GENERATED_FOR_ATTR,
            _generated_marker(reference_target.owner_prim_path, asset_url),
        )


def revert_references(
    stage: Usd.Stage,
    setup: Setup,
    target_layer: Sdf.Layer,
    reference_targets: tuple[ReferenceTarget, ...],
    asset_url: str,
    children: dict[str, list[Usd.Prim]],
    *,
    context_name: str,
    replace: bool,
) -> None:
    """Remove generated references and restore sources on the current edit target."""
    layers = _layer_index(stage)
    restore_marker = _normalize_url(asset_url)
    source_targets: dict[str, list[ReferenceTarget]] = {}
    for reference_target in reference_targets:
        if reference_target.source_reference is not None:
            source_targets.setdefault(reference_target.owner_prim_path, []).append(reference_target)
    for reference_target in reference_targets:
        if _replaces_in_place(stage, reference_target, replace=replace):
            _revert_in_place(stage, setup, layers, reference_target, asset_url, target_layer)
    for owner_path, generated in children.items():
        # Setup.remove_reference would also remove the owner override and the original reference that Append kept.
        omni.kit.commands.execute(
            "DeletePrims",
            paths=[str(child.GetPath()) for child in generated],
            context_name=context_name,
        )
        if not replace:
            continue
        for reference_target in source_targets.get(owner_path, ()):
            source, source_layer = _find_source_reference(
                stage.GetPrimAtPath(owner_path), layers, reference_target
            ) or (
                reference_target.source_reference,
                _find_layer(layers, reference_target.source_layer_identifier),
            )
            added, child_path = setup.add_new_reference(
                stage,
                Sdf.Path(owner_path),
                Sdf.ComputeAssetPathRelativeToLayer(source_layer, source.assetPath),
                str(source.primPath) if source.primPath else Setup.get_ref_default_prim_tag(),
                target_layer,
            )
            # add_new_reference omits layerOffset and customData. Revert must restore both on the same child.
            restored = Sdf.Reference(added.assetPath, source.primPath, source.layerOffset, source.customData)
            if restored != added:
                omni.kit.commands.execute(
                    "ReplaceReference",
                    stage=stage,
                    prim_path=child_path,
                    old_reference=added,
                    new_reference=restored,
                )
            _mark_child(stage.GetPrimAtPath(child_path), _RESTORED_BY_ATTR, restore_marker)
