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

__all__ = ["AssetReplaceApplyHandler"]

from lightspeed.trex.asset_replacements.core.shared import Setup
from omni.flux.job_queue.core.apply_handler_base import ApplyHandler
from omni.flux.job_queue.core.enums import ApplyOperation, ApplyPolicy
from pxr import Usd

from ..metadata import MetadataApplyReceipt, capture_metadata_receipt
from ..worker import run_in_worker_thread
from .asset_replace_apply_target import AssetReplaceApplyTarget
from .models import MeshOptimizationResult
from .reference_apply import (
    apply_atomically,
    apply_references,
    asset_metadata_paths,
    check_apply_stage,
    get_apply_stage,
    get_block_reason,
    reference_state,
    revert_atomically,
    revert_references,
)


class AssetReplaceApplyHandler(ApplyHandler[MeshOptimizationResult, AssetReplaceApplyTarget, MetadataApplyReceipt]):
    """Replace model references and write their metadata as one reversible Apply operation."""

    name = "AssetReplaceApplyHandler"
    input_type = MeshOptimizationResult
    target_type = AssetReplaceApplyTarget
    receipt_type = MetadataApplyReceipt
    apply_policy = ApplyPolicy.FOLLOW_GLOBAL

    def get_apply_block_reason(self, target: AssetReplaceApplyTarget, operation: ApplyOperation) -> str | None:
        """Return why the submitted stage cannot accept an Apply operation."""
        del operation
        return get_block_reason(target)

    async def capture_receipt(
        self,
        value: MeshOptimizationResult,
        target: AssetReplaceApplyTarget,
    ) -> MetadataApplyReceipt:
        """Capture output sidecars before the first Apply."""
        get_apply_stage(target)
        return await run_in_worker_thread(capture_metadata_receipt, asset_metadata_paths(value))

    async def apply(
        self,
        value: MeshOptimizationResult,
        target: AssetReplaceApplyTarget,
        receipt: MetadataApplyReceipt,
    ) -> None:
        """Write output sidecars and replace the source references."""
        del receipt
        stage, target_layer = get_apply_stage(target)

        def mutate() -> None:
            setup = Setup(target.context_name)
            with Usd.EditContext(stage, target_layer):
                apply_references(
                    stage,
                    setup,
                    target_layer,
                    target.reference_targets,
                    value.asset_url,
                    context_name=target.context_name,
                    replace=True,
                )

        await apply_atomically(
            asset_metadata_paths(value),
            value.validation_passed and value.texture_result.validation_passed,
            lambda: reference_state(stage, target.reference_targets, value.asset_url, replace=True)[0],
            mutate,
            "RTX Remix could not apply this modified asset. The project was restored.",
            lambda: check_apply_stage(target, stage, target_layer),
        )

    async def revert(
        self,
        value: MeshOptimizationResult,
        target: AssetReplaceApplyTarget,
        receipt: MetadataApplyReceipt,
    ) -> None:
        """Restore the source references and output sidecars."""
        stage, target_layer = get_apply_stage(target)
        children: dict[str, list[Usd.Prim]] = {}

        def classify() -> str | None:
            state, found = reference_state(stage, target.reference_targets, value.asset_url, replace=True)
            children.clear()
            children.update(found)
            return state

        def restore() -> None:
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
                    replace=True,
                )

        await revert_atomically(
            asset_metadata_paths(value),
            receipt,
            classify,
            restore,
            "RTX Remix could not revert this modified asset.",
            lambda: check_apply_stage(target, stage, target_layer),
        )
