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

__all__ = ["PackagingRepairCore"]

from collections.abc import Callable, Iterable
from contextlib import suppress
from lightspeed.trex.asset_replacements.core.shared import Setup as AssetReplacementsCore
from omni.flux.utils.common.progress import run_worker_with_latest_progress as _run_worker_with_latest_progress
from pxr import Sdf

from .authoring import RepairAuthoringCore
from .enum import PackagingRepairProgress
from .layers import RepairLayerCore
from .models import PackagingRepairRequest, PackagingRepairResult, RepairState
from .references import RepairReferenceCore
from .requests import RepairRequestCore, RepairRequestError


class PackagingRepairCore:
    """
    Core API for applying packaging repairs to editable project layers.
    """

    def __init__(self, context_name: str = ""):
        """Initialize the repair orchestrator.

        Args:
            context_name: USD context name used to inspect the active stage and validate replacements.
        """
        self._asset_core = AssetReplacementsCore(context_name=context_name)
        self._layers = RepairLayerCore(context_name=context_name)
        self._references = RepairReferenceCore(self._layers)
        self._authoring = RepairAuthoringCore(self._asset_core, self._layers)
        self._requests = RepairRequestCore(self._layers, self._references, self._authoring)

    def __del__(self):
        """Release held resources if the owner did not call ``destroy``."""
        self.destroy()

    def destroy(self):
        """Destroy held cores and release their subscriptions."""
        asset_core = getattr(self, "_asset_core", None)
        self._asset_core = None
        self._layers = None
        self._references = None
        self._authoring = None
        self._requests = None
        if asset_core is not None:
            asset_core.destroy()

    def raise_if_layers_dirty(self):
        """Raise when any live USD layer has unsaved edits.

        Raises:
            RuntimeError: If the current layer stack has pending edits.
        """
        self._layers.raise_if_layers_dirty()

    def is_file_path_valid(self, layer_identifier: str, asset_path: str, log_error: bool = True) -> bool:
        """Check whether an asset path points to a readable file.

        Args:
            layer_identifier: Identifier for the layer the asset path is relative to.
            asset_path: Asset path to inspect.
            log_error: Whether validation failures should be logged.

        Returns:
            Whether the asset path is readable.
        """
        layer = Sdf.Layer.FindOrOpen(layer_identifier)
        if not layer:
            return False
        return self._asset_core.is_file_path_valid(asset_path, layer=layer, log_error=log_error)

    def was_asset_ingested(self, asset_path: str, ignore_invalid_paths: bool = True) -> bool:
        """Check whether an asset has valid ingestion metadata.

        Args:
            asset_path: Asset path to inspect.
            ignore_invalid_paths: Whether invalid paths should be treated as ingested.

        Returns:
            Whether the asset is ingested.
        """
        return self._asset_core.was_the_asset_ingested(asset_path, ignore_invalid_paths=ignore_invalid_paths)

    def asset_is_in_project_dir(self, layer_identifier: str, asset_path: str, include_deps_dir: bool = False) -> bool:
        """Check whether an asset is inside the current project directory.

        Args:
            layer_identifier: Identifier for the layer that authored the unresolved asset.
            asset_path: Asset path to inspect.
            include_deps_dir: Whether to count the project ``deps`` directory as a project path.

        Returns:
            Whether the asset is inside the project directory.
        """
        layer = Sdf.Layer.FindOrOpen(layer_identifier)
        if not layer:
            return False
        return self._asset_core.asset_is_in_project_dir(asset_path, layer=layer, include_deps_dir=include_deps_dir)

    async def apply_async(
        self,
        repair_requests: Iterable[PackagingRepairRequest],
        progress_callback: Callable[[int, int, PackagingRepairProgress], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> PackagingRepairResult | None:
        """Apply packaging repairs on a worker thread.

        Args:
            repair_requests: Repair requests selected by the user.
            progress_callback: Optional callback receiving current item count, total item count, and progress state.
            is_cancelled: Optional callback returning whether the user requested cancellation.

        Returns:
            The repair result, or ``None`` if the repair was cancelled before saving.

        Raises:
            RuntimeError: If layers have unsaved edits or a target layer cannot be opened or saved.
        """
        self.raise_if_layers_dirty()

        state = await self._apply_repair_requests_async(
            self._layers.get_root_layer_identifier(), list(repair_requests), progress_callback, is_cancelled
        )
        if state is None:
            return None

        self._layers.reload_saved_layers(state)
        return PackagingRepairResult(ignored_items=state.ignored_items, failed_repairs=state.failed_repairs)

    def _apply_repair_requests(
        self,
        root_layer_identifier: str | None,
        repair_requests: list[PackagingRepairRequest],
        progress_callback: Callable[[int, int, PackagingRepairProgress], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        use_editable_layer_copies: bool = False,
    ) -> RepairState | None:
        state = RepairState(root_layer_identifier, is_cancelled, use_editable_layer_copies)
        total_items = max(len(repair_requests), 1)
        if progress_callback:
            progress_callback(0, total_items, PackagingRepairProgress.APPLYING)

        for index, request in enumerate(repair_requests, start=1):
            if state.is_cancelled_requested():
                return None
            # Individual repair failures are recorded on the state; keep processing the remaining requests.
            with suppress(RepairRequestError):
                self._requests.apply_repair_request(state, request)

            if state.is_cancelled_requested():
                return None
            if progress_callback:
                progress_callback(index, total_items, PackagingRepairProgress.APPLYING)

        if state.is_cancelled_requested():
            return None
        if not self._layers.save_editable_layers(state, progress_callback):
            return None

        return state

    async def _apply_repair_requests_async(
        self,
        root_layer_identifier: str | None,
        repair_requests: list[PackagingRepairRequest],
        progress_callback: Callable[[int, int, PackagingRepairProgress], None] | None,
        is_cancelled: Callable[[], bool] | None,
    ) -> RepairState | None:
        def apply_repair_requests(queue_progress: Callable[[int, int | None, PackagingRepairProgress | None], None]):
            def report_progress(current: int, total: int, status: PackagingRepairProgress):
                queue_progress(current, total, status)

            return self._apply_repair_requests(
                root_layer_identifier, repair_requests, report_progress, is_cancelled, use_editable_layer_copies=True
            )

        state = await _run_worker_with_latest_progress(
            apply_repair_requests,
            progress_callback=progress_callback,
            is_cancelled=is_cancelled,
            cancelled_result=None,
            finish_worker_on_cancel=True,
        )
        if is_cancelled and is_cancelled():
            return None
        return state
