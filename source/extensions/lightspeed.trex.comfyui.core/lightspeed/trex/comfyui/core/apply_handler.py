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

__all__ = [
    "ComfyUIAssetApplyHandler",
    "ComfyUIJobApplyHandler",
    "ComfyUITextureApplyHandler",
]

from collections.abc import Callable, Iterable
from hashlib import sha256
from typing import Any

import omni.client
import omni.kit.commands
import omni.kit.undo
import omni.usd
from lightspeed.common import constants
from lightspeed.trex.asset_pipeline.core.metadata import (
    capture_metadata_receipt,
    get_current_validation_extensions,
    revert_metadata,
    write_metadata_for_paths,
)
from lightspeed.trex.asset_pipeline.core.jobs.models import MeshOptimizationResult, TextureOptimizationResult
from lightspeed.trex.asset_pipeline.core.worker import run_in_worker_thread
from lightspeed.trex.asset_replacements.core.shared import Setup
from lightspeed.trex.texture_replacements.core.shared import TextureReplacementsCore
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core.apply_handler_base import ApplyHandler
from omni.flux.job_queue.core.enums import ApplyOperation, ApplyPolicy
from omni.flux.job_queue.core.errors import ApplyExecutionError
from omni.usd import get_context
from pxr import Sdf, Usd

from .enums import OutputApplyBehavior
from .maps import OUTPUT_TEXTURE_TYPE_MAP
from .resolvers import is_remix_reference as _is_remix_reference
from .models import (
    ComfyUIApplyReceipt,
    ComfyUIApplyTarget,
    ComfyUIAssetApplyTarget,
    ReferenceTarget,
)

_ORIGINAL = "original"
_APPLIED = "applied"
# Custom attribute Revert authors on a restored source child. Its value is the generated asset URL of the job
# that restored it, so a later Apply of that job replaces exactly that child and no other source child.
_RESTORED_BY_ATTR = "remix_comfyui_restored_by"
# Custom attribute Apply authors on every generated Remix reference child, and on a Remix reference owner that
# Replace swapped in place. Its value names the owner path and this job's generated asset URL, so classification
# finds exactly this job's children, ignores children another job appended to the same owner, recognises an
# in-place owner this job applied, and detects a generated reference that was changed by hand.
_GENERATED_FOR_ATTR = "remix_comfyui_generated_for"


def _generated_marker(owner_prim_path: str, asset_url: str) -> str:
    """Return the ``_GENERATED_FOR_ATTR`` value for one owner and one job's generated asset."""
    return f"{owner_prim_path} {_normalize_url(asset_url)}"


def _in_place_marker_attr(asset_url: str) -> str:
    """Return a separate marker attribute for each generated asset on one owner."""
    return f"{_GENERATED_FOR_ATTR}:asset_{sha256(_normalize_url(asset_url).encode()).hexdigest()}"


def _to_asset_url(value: Any) -> str | None:
    """Normalize one USD texture value for durable comparison.

    Args:
        value: USD shader input value.

    Returns:
        Authored asset URL, or ``None`` when no value exists.

    Raises:
        TypeError: If the value is not an asset path, string, or ``None``.
    """
    if value is None:
        return None
    if isinstance(value, Sdf.AssetPath):
        return value.path
    if type(value) is str:
        return value
    raise TypeError("Texture target values must be strings, Sdf.AssetPath values, or None")


def _canonical_url(layer: Sdf.Layer, asset_url: str | None) -> str | None:
    """Resolve one authored asset URL against its owning layer.

    Args:
        layer: Layer that owns the authored value.
        asset_url: Authored asset URL.

    Returns:
        Canonical asset URL, or ``None`` when no opinion exists.
    """
    if asset_url is not None and not layer.anonymous:
        return Sdf.ComputeAssetPathRelativeToLayer(layer, asset_url)
    return asset_url


def _read_texture_values(layer: Sdf.Layer, paths: Iterable[str]) -> tuple[tuple[str, str | None, str | None], ...]:
    """Read authored and canonical texture values from one exact layer.

    Args:
        layer: Submitted edit layer.
        paths: Shader input paths to inspect.

    Returns:
        ``(path, authored, canonical)`` tuples, using ``None`` for absent opinions.
    """
    values = []
    for path in paths:
        attribute = layer.GetAttributeAtPath(path)
        authored = _to_asset_url(attribute.default) if attribute is not None else None
        values.append((path, authored, _canonical_url(layer, authored)))
    return tuple(values)


def _get_apply_stage(
    target: ComfyUIApplyTarget | ComfyUIAssetApplyTarget,
) -> tuple[Usd.Stage, Sdf.Layer]:
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
            RuntimeError("No USD stage is open for this ComfyUI job"),
        )
    opened_project = str(stage.GetRootLayer().identifier)
    if opened_project != target.project_path:
        raise ApplyExecutionError(
            "This job belongs to a different project. Open the project used to create it before applying its outputs.\n"
            f"Job project: {target.project_path}\nOpened project: {opened_project}",
            RuntimeError("The open project differs from the project used to submit this ComfyUI job"),
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
            RuntimeError("The target layer used to submit this ComfyUI job is no longer in the open project"),
        )
    return stage, target_layer


def _texture_metadata_paths(value: TextureOptimizationResult) -> list[str]:
    """Return unique output URLs for one processed texture result."""
    return list(dict.fromkeys(item.asset_url for item in value.items))


def _asset_metadata_paths(value: MeshOptimizationResult) -> list[str]:
    """Return unique output URLs for the mesh and its textures."""
    return list(dict.fromkeys((value.asset_url, *(item.asset_url for item in value.texture_result.items))))


def _asset_validation_passed(value: MeshOptimizationResult) -> bool:
    """Return whether the mesh and its textures passed validation."""
    return value.validation_passed and value.texture_result.validation_passed


async def _write_output_metadata(paths: list[str], validation_passed: bool) -> None:
    """Write deterministic metadata to all outputs.

    Args:
        paths: Local or remote output files to annotate.
        validation_passed: Combined pipeline validation result.
    """
    validation_extensions = get_current_validation_extensions()
    await run_in_worker_thread(write_metadata_for_paths, paths, validation_extensions, validation_passed)


def _processed_texture_type(texture_type: TextureTypes) -> TextureTypes:
    """Return the texture type the pipeline publishes for one declared type. Every normal becomes octahedral."""
    if texture_type in (TextureTypes.NORMAL_OGL, TextureTypes.NORMAL_DX):
        return TextureTypes.NORMAL_OTH
    return texture_type


def _get_replacements(
    processed: TextureOptimizationResult,
    texture_targets: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    """Match Replace output keys to their processed textures.

    Keys are output node ids. A 3.0.5 record keyed its targets by texture type (``"albedo"``); such a key
    matches the one processed texture of that type, so a job queued before the upgrade still applies. A
    ``normal_ogl`` or ``normal_dx`` key matches the octahedral normal the pipeline converted it to.

    Args:
        processed: Complete processed texture result, including Do Nothing outputs.
        texture_targets: Replace output keys paired with exact shader input paths.

    Returns:
        Shader input and processed asset URL pairs.

    Raises:
        ValueError: If a Replace output was not produced or a texture-type key is ambiguous.
    """
    items_by_key = {item.key: item for item in processed.items}
    replacements = []
    for key, path in texture_targets:
        item = items_by_key.get(key)
        if item is None and key in OUTPUT_TEXTURE_TYPE_MAP:
            expected = _processed_texture_type(OUTPUT_TEXTURE_TYPE_MAP[key])
            matches = [
                candidate
                for candidate in processed.items
                if _processed_texture_type(candidate.texture_type) is expected
            ]
            item = matches[0] if len(matches) == 1 else None
        if item is None:
            raise ValueError("ComfyUI did not produce every Replace texture output")
        replacements.append((path, item.asset_url))
    return tuple(replacements)


async def _capture_texture_receipt(
    target_layer: Sdf.Layer,
    replacements: tuple[tuple[str, str], ...],
    metadata_paths: list[str],
) -> ComfyUIApplyReceipt:
    """Capture texture opinions and sidecars before the first Apply.

    Args:
        target_layer: Layer that owns the texture opinions.
        replacements: Shader attribute paths and processed asset URLs.
        metadata_paths: All output files whose sidecars Apply will change.

    Returns:
        A durable receipt with original opinions, original and applied comparison values, and prior sidecars.
    """
    current = _read_texture_values(target_layer, (path for path, _ in replacements))
    metadata_receipt = await run_in_worker_thread(capture_metadata_receipt, metadata_paths)
    return ComfyUIApplyReceipt(
        original_authored_values=tuple((path, authored) for path, authored, _ in current),
        original_compare_values=tuple((path, canonical) for path, _, canonical in current),
        applied_compare_values=tuple((path, _canonical_url(target_layer, url)) for path, url in replacements),
        metadata_receipt=metadata_receipt,
    )


def _verify_texture_receipt(
    replacements: tuple[tuple[str, str], ...],
    receipt: ComfyUIApplyReceipt,
    target_layer: Sdf.Layer,
) -> None:
    """Check that a texture receipt belongs to the current output and target.

    Args:
        replacements: Current output URLs and their shader attribute paths.
        receipt: Durable receipt captured before the first Apply.
        target_layer: Layer used to canonicalize replacement URLs.

    Raises:
        ApplyExecutionError: Receipt paths or applied values differ from the current replacements.
    """
    expected = dict(receipt.applied_compare_values)
    current = {path: _canonical_url(target_layer, url) for path, url in replacements}
    if set(current) != set(expected):
        raise ApplyExecutionError(
            "This job's saved Apply data no longer matches its texture targets. Submit the workflow again.",
            RuntimeError("The ComfyUI texture receipt does not match this job target"),
        )
    if current != expected:
        raise ApplyExecutionError(
            "This job's saved Apply data no longer matches its processed textures. Submit the workflow again.",
            RuntimeError("The ComfyUI texture receipt values do not match this job output"),
        )


def _raise_external_edit() -> None:
    """Raise the external-edit conflict for an Apply target.

    Raises:
        ApplyExecutionError: The current target differs from the durable receipt.
    """
    raise ApplyExecutionError(
        "A ComfyUI Apply target changed outside this job. Review the project changes and try again.",
        RuntimeError("A ComfyUI Apply target differs from its durable receipt; no changes were made"),
    )


def _check_apply_stage(
    target: ComfyUIApplyTarget | ComfyUIAssetApplyTarget, stage: Usd.Stage, target_layer: Sdf.Layer
) -> None:
    """Reject a stage or edit layer change after a sidecar await."""
    try:
        current_stage, current_layer = _get_apply_stage(target)
    except ApplyExecutionError:
        _raise_external_edit()
    if current_stage is not stage or current_layer is not target_layer:
        _raise_external_edit()


def _texture_state(target_layer: Sdf.Layer, receipt: ComfyUIApplyReceipt) -> str | None:
    """Classify the live texture values against the receipt.

    Args:
        target_layer: Submitted edit layer.
        receipt: Durable receipt captured before the first Apply.

    Returns:
        ``"original"``, ``"applied"``, or ``None`` when the receipt changes no texture.

    Raises:
        ApplyExecutionError: The live values match neither snapshot.
    """
    current = tuple(
        (path, canonical)
        for path, _, canonical in _read_texture_values(
            target_layer, (path for path, _ in receipt.applied_compare_values)
        )
    )
    if current == receipt.original_compare_values:
        return None if receipt.original_compare_values == receipt.applied_compare_values else _ORIGINAL
    if current == receipt.applied_compare_values:
        return _APPLIED
    _raise_external_edit()
    return None


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
        _raise_external_edit()
    return owner


def _replaces_in_place(stage: Usd.Stage, target: ComfyUIAssetApplyTarget, reference_target: ReferenceTarget) -> bool:
    """Return whether Replace swaps this owner's source on the owner itself: the owner is a Remix reference child.

    Raises:
        ApplyExecutionError: The owner no longer exists.
    """
    return (
        target.mesh_apply_behavior is OutputApplyBehavior.REPLACE
        and reference_target.source_reference is not None
        and _is_remix_reference(_owner_prim(stage, reference_target.owner_prim_path))
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
        return _APPLIED
    if not marked and source and not generated:
        return _ORIGINAL
    _raise_external_edit()
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
    anchor = owner.GetParent() if _is_remix_reference(owner) else owner
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
            _raise_external_edit()
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


def _reference_state(
    stage: Usd.Stage,
    target: ComfyUIAssetApplyTarget,
    asset_url: str,
) -> tuple[str | None, dict[str, list[Usd.Prim]]]:
    """Classify every owner against the reference change Apply makes.

    A Remix reference owner that Replace swaps in place is classified by ``_in_place_state``. Every other owner is
    classified by the generated children Apply creates.

    Args:
        stage: Live stage.
        target: Captured reference owners and Apply behavior.
        asset_url: Optimized asset URL that Apply references.

    Returns:
        The shared owner state and the generated children by owner path. The state is ``None`` when
        the target changes no reference.

    Raises:
        ApplyExecutionError: An owner is missing, owners disagree, an owner has more children than Apply
            created, a generated child was changed, an applied Replace owner still composes its source, or an
            original Replace owner no longer composes its source.
    """
    if target.mesh_apply_behavior is OutputApplyBehavior.NONE or not target.reference_targets:
        return None, {}
    layers = _layer_index(stage)
    states: set[str] = set()
    source_index: dict[str, dict[tuple[str, str], list[tuple[Sdf.Reference, Sdf.Layer]]]] = {}
    restored_source_index: dict[str, dict[tuple[str, str], list[tuple[Sdf.Reference, Sdf.Layer]]]] = {}
    expected_counts: dict[str, int] = {}
    replace_sources: list[ReferenceTarget] = []
    for reference_target in target.reference_targets:
        if _replaces_in_place(stage, target, reference_target):
            states.add(_in_place_state(stage, layers, reference_target, asset_url, source_index))
            continue
        if target.mesh_apply_behavior is OutputApplyBehavior.REPLACE:
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
            # No generated child: the original state, only if every Replace source is still (or again) composed.
            # A generated child that was removed by hand, without its source coming back, is an external edit.
            if not all(
                _source_composed(stage, layers, reference_target, source_index, restored_source_index)
                for reference_target in replace_sources
            ):
                _raise_external_edit()
            states.add(_ORIGINAL)
            children = {}
        elif all(len(children[owner]) == count for owner, count in expected_counts.items()):
            if any(
                _source_composed(stage, layers, reference_target, source_index, restored_source_index)
                for reference_target in replace_sources
            ):
                _raise_external_edit()
            states.add(_APPLIED)
        else:
            _raise_external_edit()
    if len(states) != 1:
        _raise_external_edit()
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


def _replace_textures(context_name: str, target_layer: Sdf.Layer, replacements: tuple[tuple[str, str], ...]) -> None:
    """Author processed textures on the submitted edit layer."""
    if replacements:
        TextureReplacementsCore(context_name).replace_textures(
            list(replacements),
            force=False,
            target_layer=target_layer,
        )


def _restore_textures(context_name: str, target_layer: Sdf.Layer, receipt: ComfyUIApplyReceipt) -> None:
    """Restore the exact original texture opinions from the receipt."""
    if not receipt.original_authored_values:
        return
    current = _read_texture_values(target_layer, (path for path, _ in receipt.original_authored_values))
    TextureReplacementsCore(context_name).replace_textures(
        list(receipt.original_authored_values),
        force=True,
        target_layer=target_layer,
        expected_current_textures=[(path, authored) for path, authored, _ in current],
    )


def _find_layer(layers: dict[str, Sdf.Layer], identifier: str) -> Sdf.Layer:
    """Return the project layer with one exact identifier.

    Raises:
        ApplyExecutionError: The layer is not in the project layer stack.
    """
    layer = layers.get(identifier)
    if layer is None:
        raise ApplyExecutionError(
            "A source layer used by this job is no longer available. Restore it before applying the asset.",
            RuntimeError("A captured ComfyUI source reference layer is not in the project layer stack"),
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


def _get_block_reason(target: ComfyUIApplyTarget | ComfyUIAssetApplyTarget) -> str | None:
    """Return why the submitted stage cannot accept an Apply operation."""
    try:
        _get_apply_stage(target)
    except ApplyExecutionError as error:
        return error.reason
    return None


async def _apply_atomically(
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
        classify: Returns the live target state; called before and after the sidecar await.
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
            _raise_external_edit()
        if state == _ORIGINAL:
            _run_undoable(mutate)
    except BaseException as error:
        await run_in_worker_thread(revert_metadata, metadata_rollback)
        if not isinstance(error, Exception) or isinstance(error, ApplyExecutionError):
            raise
        raise ApplyExecutionError(failure_message, error) from error


async def _revert_atomically(
    metadata_paths: list[str],
    receipt: ComfyUIApplyReceipt,
    classify: Callable[[], str | None],
    restore: Callable[[], None],
    failure_message: str,
    check_stage: Callable[[], None],
) -> None:
    """Restore sidecars inside the recovery boundary, re-check the target, then the stage in one undo group.

    Args:
        metadata_paths: Output files whose sidecars Revert restores.
        receipt: Durable receipt from the first Apply.
        classify: Returns the live target state; called before and after the sidecar await.
        restore: Synchronous stage restore for an applied target.
        failure_message: User-facing message if the stage restore fails.
        check_stage: Rejects a stage or edit layer change after the sidecar await.

    Raises:
        ApplyExecutionError: The target changed outside this job, or the stage restore failed; sidecars re-applied.
        BaseException: Cancellation and other non-Exception failures, after the sidecar re-apply.
    """
    state = classify()
    metadata_rollback = await run_in_worker_thread(capture_metadata_receipt, metadata_paths)
    try:
        # Inside the boundary: a sidecar that fails after an earlier one was restored rolls back to the pre-attempt files.
        await run_in_worker_thread(revert_metadata, receipt.metadata_receipt)
        check_stage()
        if classify() != state:
            _raise_external_edit()
        if state == _APPLIED:
            _run_undoable(restore)
    except BaseException as error:
        await run_in_worker_thread(revert_metadata, metadata_rollback)
        if not isinstance(error, Exception) or isinstance(error, ApplyExecutionError):
            raise
        raise ApplyExecutionError(failure_message, error) from error


class ComfyUITextureApplyHandler(ApplyHandler[TextureOptimizationResult, ComfyUIApplyTarget, ComfyUIApplyReceipt]):
    """Write all texture metadata and replace only the Replace texture outputs."""

    name = "ComfyUITextureApplyHandler"
    input_type = TextureOptimizationResult
    target_type = ComfyUIApplyTarget
    receipt_type = ComfyUIApplyReceipt
    apply_policy = ApplyPolicy.FOLLOW_GLOBAL

    def get_apply_block_reason(self, target: ComfyUIApplyTarget, operation: ApplyOperation) -> str | None:
        """Return why the submitted stage cannot accept an Apply operation."""
        del operation
        return _get_block_reason(target)

    async def capture_receipt(
        self,
        value: TextureOptimizationResult,
        target: ComfyUIApplyTarget,
    ) -> ComfyUIApplyReceipt:
        """Capture texture and metadata state before the first Apply.

        Args:
            value: All processed textures.
            target: Captured project, edit layer, and Replace shader attribute paths.

        Returns:
            A durable receipt for Reapply conflict checks and Revert.

        Raises:
            ApplyExecutionError: The submitted stage or edit layer is unavailable.
            ValueError: A Replace output was not produced.
        """
        replacements = _get_replacements(value, target.texture_targets)
        _stage, target_layer = _get_apply_stage(target)
        return await _capture_texture_receipt(target_layer, replacements, _texture_metadata_paths(value))

    async def apply(
        self,
        value: TextureOptimizationResult,
        target: ComfyUIApplyTarget,
        receipt: ComfyUIApplyReceipt,
    ) -> None:
        """Write every sidecar, then author the Replace textures when they are still original.

        Args:
            value: All processed textures.
            target: Captured project, edit layer, and Replace shader attribute paths.
            receipt: Durable receipt captured before the first Apply.

        Raises:
            ApplyExecutionError: The target changed outside this job, or Apply failed and was rolled back.
        """
        replacements = _get_replacements(value, target.texture_targets)
        _stage, target_layer = _get_apply_stage(target)
        _verify_texture_receipt(replacements, receipt, target_layer)
        await _apply_atomically(
            _texture_metadata_paths(value),
            value.validation_passed,
            lambda: _texture_state(target_layer, receipt),
            lambda: _replace_textures(target.context_name, target_layer, replacements),
            "RTX Remix could not apply these textures. The project was restored.",
            lambda: _check_apply_stage(target, _stage, target_layer),
        )

    async def revert(
        self,
        value: TextureOptimizationResult,
        target: ComfyUIApplyTarget,
        receipt: ComfyUIApplyReceipt,
    ) -> None:
        """Restore original texture opinions and sidecars when no external edit exists.

        Args:
            value: Processed texture result used to check receipt ownership.
            target: Captured project, edit layer, and Replace shader attribute paths.
            receipt: Durable receipt from the first Apply.

        Raises:
            ApplyExecutionError: The target changed outside this job, or the texture restore failed.
        """
        replacements = _get_replacements(value, target.texture_targets)
        _stage, target_layer = _get_apply_stage(target)
        _verify_texture_receipt(replacements, receipt, target_layer)
        await _revert_atomically(
            _texture_metadata_paths(value),
            receipt,
            lambda: _texture_state(target_layer, receipt),
            lambda: _restore_textures(target.context_name, target_layer, receipt),
            "RTX Remix could not revert these textures.",
            lambda: _check_apply_stage(target, _stage, target_layer),
        )


class ComfyUIAssetApplyHandler(ApplyHandler[MeshOptimizationResult, ComfyUIAssetApplyTarget, ComfyUIApplyReceipt]):
    """Apply model references and standalone textures as one undoable stage change."""

    name = "ComfyUIAssetApplyHandler"
    input_type = MeshOptimizationResult
    target_type = ComfyUIAssetApplyTarget
    receipt_type = ComfyUIApplyReceipt
    apply_policy = ApplyPolicy.FOLLOW_GLOBAL

    def get_apply_block_reason(self, target: ComfyUIAssetApplyTarget, operation: ApplyOperation) -> str | None:
        """Return why the submitted stage cannot accept an asset Apply operation."""
        del operation
        return _get_block_reason(target)

    async def capture_receipt(
        self,
        value: MeshOptimizationResult,
        target: ComfyUIAssetApplyTarget,
    ) -> ComfyUIApplyReceipt:
        """Capture texture and sidecar state before the first Apply.

        Args:
            value: Complete optimized mesh and texture results.
            target: Captured owners, source references, and texture attribute paths.

        Returns:
            A durable receipt for Reapply conflict checks and Revert.

        Raises:
            ApplyExecutionError: The stage or edit layer is unavailable.
            ValueError: A Replace output was not produced.
        """
        _stage, target_layer = _get_apply_stage(target)
        replacements = _get_replacements(value.texture_result, target.texture_targets)
        return await _capture_texture_receipt(target_layer, replacements, _asset_metadata_paths(value))

    @staticmethod
    def _classify(
        stage: Usd.Stage,
        target_layer: Sdf.Layer,
        target: ComfyUIAssetApplyTarget,
        receipt: ComfyUIApplyReceipt,
        asset_url: str,
    ) -> tuple[str | None, dict[str, list[Usd.Prim]]]:
        """Classify references and textures together.

        Returns:
            The shared state and generated children by owner. The state is ``None`` when Apply changes nothing.

        Raises:
            ApplyExecutionError: References and textures disagree, or either changed outside this job.
        """
        reference_state, children = _reference_state(stage, target, asset_url)
        texture_state = _texture_state(target_layer, receipt)
        states = {state for state in (reference_state, texture_state) if state is not None}
        if len(states) > 1:
            _raise_external_edit()
        return (states.pop() if states else None), children

    async def apply(
        self,
        value: MeshOptimizationResult,
        target: ComfyUIAssetApplyTarget,
        receipt: ComfyUIApplyReceipt,
    ) -> None:
        """Write every sidecar, then add or replace references and textures in one undo group.

        Args:
            value: Complete optimized mesh and texture results.
            target: Captured project, owners, source references, and texture paths.
            receipt: Durable receipt captured before the first Apply.

        Raises:
            ApplyExecutionError: The target changed outside this job, or Apply failed and was rolled back.

        An already applied target receives fresh metadata without another stage mutation.
        """
        stage, target_layer = _get_apply_stage(target)
        replacements = _get_replacements(value.texture_result, target.texture_targets)
        _verify_texture_receipt(replacements, receipt, target_layer)

        def mutate() -> None:
            setup = Setup(target.context_name)
            layers = _layer_index(stage)
            with Usd.EditContext(stage, target_layer):
                # Mesh Do Nothing never touches references. Only Replace textures are authored.
                references = () if target.mesh_apply_behavior is OutputApplyBehavior.NONE else target.reference_targets
                last_references = {reference.owner_prim_path: reference for reference in references}
                for reference_target in references:
                    owner_path = Sdf.Path(reference_target.owner_prim_path)
                    if (
                        target.mesh_apply_behavior is OutputApplyBehavior.REPLACE
                        and reference_target.source_reference is not None
                    ):
                        owner = stage.GetPrimAtPath(owner_path)
                        # A previous Revert of this job composes the source as a marked Remix reference child.
                        # Replace must remove that child too, or both models stay composed after
                        # Apply -> Revert -> Apply.
                        restored = _restored_source_children(stage, layers, reference_target, value.asset_url)
                        if restored:
                            omni.kit.commands.execute("DeletePrims", paths=restored, context_name=target.context_name)
                        source, source_layer = _find_source_reference(owner, layers, reference_target) or (
                            reference_target.source_reference,
                            _find_layer(layers, reference_target.source_layer_identifier),
                        )
                        # Remove every selected source before creating one generated child for this owner.
                        if reference_target != last_references[reference_target.owner_prim_path]:
                            setup.remove_selected_reference(stage, owner_path, source, source_layer)
                            continue
                        if _is_remix_reference(owner):
                            # A Remix reference owner is replaced in place: it keeps its path and its other
                            # references, and only the source becomes the generated model. No sibling is created.
                            _replace_reference_in_place(
                                stage,
                                setup,
                                owner,
                                source,
                                source_layer,
                                _relative_reference(target_layer, value.asset_url),
                            )
                            child_path = owner_path
                        else:
                            _added, child_path = setup.replace_reference(
                                stage,
                                owner_path,
                                source,
                                source_layer,
                                value.asset_url,
                                target_layer,
                                preserve_other_references=True,
                                use_undo_group=False,
                            )
                    else:
                        _added, child_path = setup.add_new_reference(
                            stage,
                            owner_path,
                            value.asset_url,
                            Setup.get_ref_default_prim_tag(),
                            target_layer,
                        )
                    _mark_child(
                        stage.GetPrimAtPath(child_path),
                        _in_place_marker_attr(value.asset_url) if child_path == owner_path else _GENERATED_FOR_ATTR,
                        _generated_marker(reference_target.owner_prim_path, value.asset_url),
                    )
            _replace_textures(target.context_name, target_layer, replacements)

        await _apply_atomically(
            _asset_metadata_paths(value),
            _asset_validation_passed(value),
            lambda: self._classify(stage, target_layer, target, receipt, value.asset_url)[0],
            mutate,
            "RTX Remix could not apply this generated asset. The project was restored.",
            lambda: _check_apply_stage(target, stage, target_layer),
        )

    async def revert(
        self,
        value: MeshOptimizationResult,
        target: ComfyUIAssetApplyTarget,
        receipt: ComfyUIApplyReceipt,
    ) -> None:
        """Remove generated references, restore textures and sidecars.

        Args:
            value: Complete asset result used to identify generated children and check the receipt.
            target: Captured project, owners, source references, and texture paths.
            receipt: Durable receipt from the first Apply.

        Raises:
            ApplyExecutionError: The target changed outside this job, or the stage restore failed.

        A reverted Replace composes the source model again: on the owner itself when the owner is a Remix
        reference child that Apply replaced in place, otherwise as a marked Remix reference child of its owner.
        """
        stage, target_layer = _get_apply_stage(target)
        replacements = _get_replacements(value.texture_result, target.texture_targets)
        _verify_texture_receipt(replacements, receipt, target_layer)
        children: dict[str, list[Usd.Prim]] = {}

        def classify() -> str | None:
            state, found = self._classify(stage, target_layer, target, receipt, value.asset_url)
            children.clear()
            children.update(found)
            return state

        def restore() -> None:
            setup = Setup(target.context_name)
            layers = _layer_index(stage)
            restore_marker = _normalize_url(value.asset_url)
            source_targets: dict[str, list[ReferenceTarget]] = {}
            for reference_target in target.reference_targets:
                if reference_target.source_reference is not None:
                    source_targets.setdefault(reference_target.owner_prim_path, []).append(reference_target)
            with Usd.EditContext(stage, target_layer):
                for reference_target in target.reference_targets:
                    if _replaces_in_place(stage, target, reference_target):
                        _revert_in_place(stage, setup, layers, reference_target, value.asset_url, target_layer)
                for owner_path, generated in children.items():
                    # DeletePrims removes only the generated child specs. Setup.remove_reference would also
                    # remove the owner override, and with it the original reference an Append kept.
                    omni.kit.commands.execute(
                        "DeletePrims",
                        paths=[str(child.GetPath()) for child in generated],
                        context_name=target.context_name,
                    )
                    if target.mesh_apply_behavior is not OutputApplyBehavior.REPLACE:
                        continue
                    for reference_target in source_targets.get(owner_path, ()):
                        source, source_layer = _find_source_reference(
                            stage.GetPrimAtPath(owner_path), layers, reference_target
                        ) or (
                            reference_target.source_reference,
                            _find_layer(layers, reference_target.source_layer_identifier),
                        )
                        # The source returns as a new marked child of the owner.
                        added, child_path = setup.add_new_reference(
                            stage,
                            Sdf.Path(owner_path),
                            Sdf.ComputeAssetPathRelativeToLayer(source_layer, source.assetPath),
                            str(source.primPath) if source.primPath else Setup.get_ref_default_prim_tag(),
                            target_layer,
                        )
                        # add_new_reference authors only assetPath and primPath. Restore the captured offset
                        # and customData on the same child so Revert composes the full source reference.
                        restored = Sdf.Reference(
                            added.assetPath, source.primPath, source.layerOffset, source.customData
                        )
                        if restored != added:
                            omni.kit.commands.execute(
                                "ReplaceReference",
                                stage=stage,
                                prim_path=child_path,
                                old_reference=added,
                                new_reference=restored,
                            )
                        _mark_child(stage.GetPrimAtPath(child_path), _RESTORED_BY_ATTR, restore_marker)
            _restore_textures(target.context_name, target_layer, receipt)

        await _revert_atomically(
            _asset_metadata_paths(value),
            receipt,
            classify,
            restore,
            "RTX Remix could not revert this generated asset.",
            lambda: _check_apply_stage(target, stage, target_layer),
        )


class ComfyUIJobApplyHandler(ComfyUITextureApplyHandler):
    """Released 3.0.5 handler identity. Records written before 3.0.6 resolve to the texture handler."""

    name = "ComfyUIJobApplyHandler"
