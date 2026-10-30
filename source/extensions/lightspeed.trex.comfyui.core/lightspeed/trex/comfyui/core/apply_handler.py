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

from collections.abc import Iterable
from typing import Any

from lightspeed.trex.asset_pipeline.core.jobs.models import MeshOptimizationResult, TextureOptimizationResult
from lightspeed.trex.asset_pipeline.core.jobs.reference_apply import (
    APPLIED as _APPLIED,
    ORIGINAL as _ORIGINAL,
    apply_atomically as _apply_atomically,
    apply_references,
    asset_metadata_paths as _asset_metadata_paths,
    check_apply_stage as _check_apply_stage,
    get_apply_stage as _get_apply_stage,
    get_block_reason as _get_block_reason,
    raise_external_edit as _raise_external_edit,
    reference_state as _reference_state,
    revert_atomically as _revert_atomically,
    revert_references,
)
from lightspeed.trex.asset_pipeline.core.metadata import capture_metadata_receipt
from lightspeed.trex.asset_pipeline.core.worker import run_in_worker_thread
from lightspeed.trex.asset_replacements.core.shared import Setup
from lightspeed.trex.texture_replacements.core.shared import TextureReplacementsCore
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core.apply_handler_base import ApplyHandler
from omni.flux.job_queue.core.enums import ApplyOperation, ApplyPolicy
from omni.flux.job_queue.core.errors import ApplyExecutionError
from pxr import Sdf, Usd

from .enums import OutputApplyBehavior
from .maps import OUTPUT_TEXTURE_TYPE_MAP
from .models import (
    ComfyUIApplyReceipt,
    ComfyUIApplyTarget,
    ComfyUIAssetApplyTarget,
)


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


def _texture_metadata_paths(value: TextureOptimizationResult) -> list[str]:
    """Return unique output URLs for one processed texture result."""
    return list(dict.fromkeys(item.asset_url for item in value.items))


def _asset_validation_passed(value: MeshOptimizationResult) -> bool:
    """Return whether the mesh and its textures passed validation."""
    return value.validation_passed and value.texture_result.validation_passed


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
            receipt.metadata_receipt,
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
        reference_state, children = (
            (None, {})
            if target.mesh_apply_behavior is OutputApplyBehavior.NONE
            else _reference_state(
                stage,
                target.reference_targets,
                asset_url,
                replace=target.mesh_apply_behavior is OutputApplyBehavior.REPLACE,
            )
        )
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
            """Apply references and standalone textures for this job."""
            setup = Setup(target.context_name)
            with Usd.EditContext(stage, target_layer):
                if target.mesh_apply_behavior is not OutputApplyBehavior.NONE:
                    apply_references(
                        stage,
                        setup,
                        target_layer,
                        target.reference_targets,
                        value.asset_url,
                        context_name=target.context_name,
                        replace=target.mesh_apply_behavior is OutputApplyBehavior.REPLACE,
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
            """Classify references and retain this job's generated children."""
            state, found = self._classify(stage, target_layer, target, receipt, value.asset_url)
            children.clear()
            children.update(found)
            return state

        def restore() -> None:
            """Restore references and standalone textures for this job."""
            setup = Setup(target.context_name)
            with Usd.EditContext(stage, target_layer):
                revert_references(
                    stage,
                    setup,
                    target_layer,
                    target.reference_targets,
                    value.asset_url,
                    children,
                    context_name=target.context_name,
                    replace=target.mesh_apply_behavior is OutputApplyBehavior.REPLACE,
                )
            _restore_textures(target.context_name, target_layer, receipt)

        await _revert_atomically(
            _asset_metadata_paths(value),
            receipt.metadata_receipt,
            classify,
            restore,
            "RTX Remix could not revert this generated asset.",
            lambda: _check_apply_stage(target, stage, target_layer),
        )


class ComfyUIJobApplyHandler(ComfyUITextureApplyHandler):
    """Released 3.0.5 handler identity. Records written before 3.0.6 resolve to the texture handler."""

    name = "ComfyUIJobApplyHandler"
