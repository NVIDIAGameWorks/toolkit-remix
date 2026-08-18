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

__all__ = ["ComfyUIJobApplyHandler"]

from typing import Any

from lightspeed.trex.asset_pipeline.core.models import TextureProcessingResult
from lightspeed.trex.texture_replacements.core.shared import TextureReplacementsCore
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core.apply_handler_base import ApplyHandler
from omni.flux.job_queue.core.enums import ApplyOperation, ApplyPolicy
from omni.flux.job_queue.core.errors import ApplyExecutionError
from omni.usd import get_context
from pxr import Sdf, Usd

from .maps import OUTPUT_TEXTURE_TYPE_MAP
from .models import ComfyUIApplyReceipt, ComfyUIApplyTarget


def _to_asset_url(value: Any) -> str | None:
    """Normalize a USD texture value for durable comparison.

    Args:
        value: USD shader input value.

    Returns:
        Authored asset URL, or None when no value exists.

    Raises:
        TypeError: If the authored value is not a supported asset-path representation.
    """
    if value is None:
        return None
    if isinstance(value, Sdf.AssetPath):
        return value.path
    if type(value) is str:
        return value
    raise TypeError("Texture target values must be strings, Sdf.AssetPath values, or None")


def _canonicalize_asset_url(layer: Sdf.Layer, value: str | Sdf.AssetPath | None) -> str | None:
    """Resolve one authored asset URL against its owning layer.

    Args:
        layer: Layer that owns the authored value.
        value: Supported authored asset-path representation.

    Returns:
        Canonical asset URL, or None when no opinion exists.

    Raises:
        TypeError: If the authored value is not a supported asset-path representation.
    """
    asset_url = _to_asset_url(value)
    if asset_url is not None and not layer.anonymous:
        return Sdf.ComputeAssetPathRelativeToLayer(layer, asset_url)
    return asset_url


def _get_apply_stage(target: ComfyUIApplyTarget) -> tuple[Usd.Stage, Sdf.Layer]:
    """Resolve the live stage only when it matches the submitted Apply target.

    Args:
        target: Persisted project and edit-layer identity.

    Returns:
        Matching live stage and edit layer.

    Raises:
        ApplyExecutionError: If the submitted project is not current or its target layer is no longer loaded.
    """
    stage = get_context(target.context_name).get_stage()
    if stage is None:
        raise ApplyExecutionError(
            "Open the project used to create this job before applying its processed textures.",
            RuntimeError("No USD stage is open for this ComfyUI job"),
        )
    root_layer = stage.GetRootLayer()
    opened_project = str(root_layer.identifier)
    if opened_project != target.project_path:
        raise ApplyExecutionError(
            "This job belongs to a different project. "
            "Open the project used to create it before applying its processed textures.\n"
            f"Job project: {target.project_path}\n"
            f"Opened project: {opened_project}",
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
            "The edit layer used to create this job is unavailable. Restore that layer before applying its processed textures.",
            RuntimeError("The target layer used to submit this ComfyUI job is no longer in the open project"),
        )
    return stage, target_layer


def _read_compare_values(layer: Sdf.Layer, paths: tuple[str, ...]) -> tuple[tuple[str, str | None], ...]:
    """Read canonical values from the exact target layer for conflict comparisons.

    Args:
        layer: Submitted edit layer.
        paths: Shader input paths to inspect.

    Returns:
        Paths paired with canonical values, using None for absent opinions.
    """
    values = []
    for path in paths:
        attribute = layer.GetAttributeAtPath(path)
        value = _canonicalize_asset_url(layer, attribute.default) if attribute is not None else None
        values.append((path, value))
    return tuple(values)


def _read_exact_authored_values(layer: Sdf.Layer, paths: tuple[str, ...]) -> tuple[tuple[str, str | None], ...]:
    """Read the exact target-layer spellings used as a forced-write CAS baseline."""
    return tuple(
        (
            path,
            _to_asset_url(attribute.default) if (attribute := layer.GetAttributeAtPath(path)) is not None else None,
        )
        for path in paths
    )


class ComfyUIJobApplyHandler(ApplyHandler):
    """Apply and safely revert processed ComfyUI textures."""

    name = "ComfyUIJobApplyHandler"
    input_type = TextureProcessingResult
    target_type = ComfyUIApplyTarget
    receipt_type = ComfyUIApplyReceipt
    apply_policy = ApplyPolicy.FOLLOW_GLOBAL

    def get_apply_block_reason(self, target: ComfyUIApplyTarget, operation: ApplyOperation) -> str | None:
        """Return why the exact submitted stage cannot currently accept an Apply operation.

        Args:
            target: Captured stage, edit layer, and shader inputs.
            operation: Exact Apply, Reapply, or Revert operation being considered.

        Returns:
            User-facing recovery guidance, or ``None`` when the exact target is available.
        """
        try:
            _get_apply_stage(target)
        except ApplyExecutionError as error:
            return error.reason
        return None

    @staticmethod
    def _get_replacements(value: TextureProcessingResult, target: ComfyUIApplyTarget) -> tuple[tuple[str, str], ...]:
        """Match every processed texture key to one compatible captured shader input.

        The asset pipeline preserves caller keys while converting DirectX and OpenGL normals to octahedral normals.
        Every other output must retain its declared texture semantic.

        Args:
            value: Fully processed textures.
            target: Captured shader input mapping.

        Returns:
            Shader input and processed asset URL pairs.

        Raises:
            ValueError: If processed textures are duplicated, incompatible, unsupported, or incomplete.
        """
        target_by_key = dict(target.texture_targets)
        if not target_by_key:
            raise ValueError("ComfyUI Apply requires at least one texture target")
        if len(target_by_key) != len(target.texture_targets):
            raise ValueError("ComfyUI Apply texture target keys must be unique")
        items_by_key = {}
        for item in value.items:
            if item.key not in target_by_key:
                raise ValueError("ComfyUI produced an unexpected processed texture")
            expected_texture_type = OUTPUT_TEXTURE_TYPE_MAP.get(item.key)
            final_texture_type = (
                TextureTypes.NORMAL_OTH
                if expected_texture_type in (TextureTypes.NORMAL_DX, TextureTypes.NORMAL_OGL)
                else expected_texture_type
            )
            if item.texture_type is not final_texture_type:
                raise ValueError(f"ComfyUI processed texture '{item.key}' is incompatible with its material input")
            if item.key in items_by_key:
                raise ValueError(f"ComfyUI produced more than one {item.key} texture")
            items_by_key[item.key] = item
        if items_by_key.keys() != target_by_key.keys():
            raise ValueError("ComfyUI did not produce every required processed texture")
        return tuple((path, items_by_key[key].asset_url) for key, path in target.texture_targets)

    @staticmethod
    def _raise_external_edit() -> None:
        """Raise the user-facing conflict reported by Apply and Revert.

        Raises:
            ApplyExecutionError: Always, because the target changed outside this job.
        """
        raise ApplyExecutionError(
            "A texture target changed outside this ComfyUI job. Review the project changes and try again.",
            RuntimeError("A ComfyUI texture target differs from its durable Apply receipt; no changes were made"),
        )

    @staticmethod
    def _expected_values(
        target_layer: Sdf.Layer,
        replacements: tuple[tuple[str, str], ...],
    ) -> tuple[tuple[str, str | None], ...]:
        """Canonicalize processed texture values before the durable receipt is stored.

        Args:
            target_layer: Exact persisted layer that will own the authored values.
            replacements: Validated shader input and processed asset URL pairs.

        Returns:
            Canonical values expected after Apply.
        """
        return tuple((path, _canonicalize_asset_url(target_layer, asset_url)) for path, asset_url in replacements)

    async def capture_receipt(
        self,
        value: TextureProcessingResult,
        target: ComfyUIApplyTarget,
    ) -> ComfyUIApplyReceipt:
        """Capture the target-layer baseline and expected values without authoring USD.

        Args:
            value: Fully processed textures.
            target: Exact project and shader inputs captured at submission.

        Returns:
            Receipt ready to persist before Apply mutates the target layer.

        Raises:
            ValueError: If processed textures do not match the target.
            ApplyExecutionError: If the submitted project target is unavailable.
        """
        replacements = self._get_replacements(value, target)
        _stage, target_layer = _get_apply_stage(target)
        target_paths = tuple(path for path, _ in replacements)
        original_authored_values = _read_exact_authored_values(target_layer, target_paths)
        return ComfyUIApplyReceipt(
            original_authored_values=original_authored_values,
            original_compare_values=tuple(
                (path, _canonicalize_asset_url(target_layer, authored_value))
                for path, authored_value in original_authored_values
            ),
            applied_compare_values=self._expected_values(target_layer, replacements),
        )

    @staticmethod
    def _verify_receipt_target(target_paths: tuple[str, ...], receipt: ComfyUIApplyReceipt) -> None:
        """Reject a receipt that does not describe the exact current Apply target.

        Args:
            target_paths: Shader inputs captured by the current job target.
            receipt: Persisted receipt from an earlier Apply.

        Raises:
            ApplyExecutionError: If the saved Apply data does not describe the current target.
        """
        authored_paths = tuple(path for path, _ in receipt.original_authored_values)
        original_paths = tuple(path for path, _ in receipt.original_compare_values)
        applied_paths = tuple(path for path, _ in receipt.applied_compare_values)
        target_path_set = set(target_paths)
        if (
            set(authored_paths) != target_path_set
            or set(original_paths) != target_path_set
            or set(applied_paths) != target_path_set
        ):
            raise ApplyExecutionError(
                "This job's saved Apply data no longer matches its texture targets. Submit the material again.",
                RuntimeError("The ComfyUI Apply receipt does not match this job target"),
            )

    async def apply(
        self,
        value: TextureProcessingResult,
        target: ComfyUIApplyTarget,
        receipt: ComfyUIApplyReceipt,
    ) -> None:
        """Idempotently apply processed textures using a durable pre-mutation receipt.

        Args:
            value: Fully processed textures.
            target: Exact project and shader inputs captured at submission.
            receipt: Durable receipt stored before the first Apply attempt.

        Raises:
            ValueError: If processed textures do not match the target.
            ApplyExecutionError: If the project target changed or Reapply detects an external edit.
        """
        replacements = self._get_replacements(value, target)
        _stage, target_layer = _get_apply_stage(target)
        self._verify_receipt_target(tuple(path for path, _ in replacements), receipt)
        replacements_by_path = dict(replacements)
        ordered_replacements = tuple((path, replacements_by_path[path]) for path, _ in receipt.applied_compare_values)
        if self._expected_values(target_layer, ordered_replacements) != receipt.applied_compare_values:
            raise ApplyExecutionError(
                "This job's saved Apply data no longer matches its processed textures. Submit the material again.",
                RuntimeError("The ComfyUI Apply receipt values do not match this job output"),
            )
        current_values = _read_compare_values(
            target_layer,
            tuple(path for path, _ in receipt.applied_compare_values),
        )
        if current_values == receipt.applied_compare_values:
            return
        if current_values != receipt.original_compare_values:
            self._raise_external_edit()
        TextureReplacementsCore(target.context_name).replace_textures(
            list(ordered_replacements),
            force=False,
            target_layer=target_layer,
        )

    async def revert(
        self,
        value: TextureProcessingResult,
        target: ComfyUIApplyTarget,
        receipt: ComfyUIApplyReceipt,
    ) -> None:
        """Restore pre-first-Apply values when the applied values remain current.

        Args:
            value: Processed textures retained by the queue; validated by the generic Apply contract.
            target: Exact project and shader inputs captured at submission.
            receipt: Durable receipt from the most recent successful Apply.

        Raises:
            ApplyExecutionError: If the project target or an applied texture changed.
        """
        _stage, target_layer = _get_apply_stage(target)
        target_paths = tuple(path for _, path in target.texture_targets)
        self._verify_receipt_target(target_paths, receipt)
        expected_current_values = _read_exact_authored_values(target_layer, target_paths)
        current_values = tuple(
            (path, _canonicalize_asset_url(target_layer, value)) for path, value in expected_current_values
        )
        if expected_current_values == receipt.original_authored_values:
            return
        if current_values != receipt.applied_compare_values:
            self._raise_external_edit()
        TextureReplacementsCore(target.context_name).replace_textures(
            list(receipt.original_authored_values),
            force=True,
            target_layer=target_layer,
            expected_current_textures=list(expected_current_values),
        )
