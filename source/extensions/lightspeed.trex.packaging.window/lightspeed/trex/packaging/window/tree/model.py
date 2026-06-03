"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["HEADER_DICT", "PackagingErrorModel"]

from collections.abc import Callable

import omni.kit.app
from lightspeed.trex.asset_replacements.core.shared.data_models import (
    AssetReplacementsValidators,
    ReplacementAssetType,
)
from lightspeed.trex.packaging.core import PackagingRepairCore
from lightspeed.trex.packaging.core.repair import PackagingRepairProgress, PackagingRepairRequest, PackagingRepairResult
from omni import ui
from omni.flux.utils.common import Event, EventSubscription, reset_default_attrs
from pxr import Sdf

from .item import PackagingErrorItem

HEADER_DICT = {0: "Prim Path", 1: "Unresolved Path", 2: "Updated Path", 3: "Action"}


class PackagingErrorModel(ui.AbstractItemModel):
    def __init__(self, context_name: str = ""):
        super().__init__()

        self.default_attr = {
            "_context_name": None,
            "_items": [],
            "_repair_core": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._items = []
        self._repair_core = PackagingRepairCore(context_name=context_name)

        self.__on_action_changed = Event()

    def refresh(self, unresolved_assets: list[tuple[str, str, str]]):
        """Refresh the model with unresolved assets.

        Args:
            unresolved_assets: Tuples containing layer identifier, prim path, and unresolved asset path.
        """
        self._items = [PackagingErrorItem(layer, path, asset) for layer, path, asset in unresolved_assets]
        self._item_changed(None)

    def replace_asset_paths(self, items: dict[PackagingErrorItem, str]):
        """Replace the selected asset paths.

        Args:
            items: Mapping of error items to replacement asset paths.
        """
        for item, new_path in items.items():
            item.fixed_asset_path = new_path
        self.__on_action_changed()

    def remove_asset_paths(self, items: list[PackagingErrorItem]):
        """Remove the fixed asset paths for the given items.

        Args:
            items: Error items to remove from the repaired output.
        """
        for item in items:
            item.fixed_asset_path = None
        self.__on_action_changed()

    def reset_asset_paths(self, items: list[PackagingErrorItem] | None):
        """Reset the fixed asset paths to their original asset paths.

        Args:
            items: Error items to reset, or ``None`` to reset all items.
        """
        for item in items if items is not None else self._items:
            item.fixed_asset_path = item.asset_path
        self.__on_action_changed()

    async def apply_new_paths_async(
        self,
        items: list[PackagingErrorItem] | None = None,
        progress_callback: Callable[[int, int, PackagingRepairProgress], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> PackagingRepairResult | None:
        """Apply fixed asset paths while keeping repair authoring off the UI thread.

        Args:
            items: Error items to apply, or ``None`` to apply all items.
            progress_callback: Optional callback receiving current item count, total item count, and progress state.
            is_cancelled: Optional callback returning whether the user requested cancellation.

        Returns:
            Repair result, or ``None`` when cancelled.

        Raises:
            RuntimeError: If layers have unsaved edits or a target layer cannot be opened or saved.
        """
        repair_requests = self.__get_repair_requests(items)
        self._repair_core.raise_if_layers_dirty()
        if progress_callback:
            progress_callback(0, max(len(repair_requests), 1), PackagingRepairProgress.APPLYING)
            # Let Kit place and paint the progress dialog before the worker starts.
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()

        result = await self._repair_core.apply_async(
            repair_requests, progress_callback=progress_callback, is_cancelled=is_cancelled
        )
        if result is None:
            return None

        self.__on_action_changed()
        return result

    @property
    def context_name(self) -> str:
        """Get the USD context name.

        Returns:
            The context name used by the repair core.
        """
        return self._context_name

    @staticmethod
    def get_layer(item: PackagingErrorItem) -> Sdf.Layer | None:
        """Get the layer associated with an error item.

        Args:
            item: The item whose layer should be opened.

        Returns:
            The item's layer, or ``None`` if it cannot be opened.
        """
        return Sdf.Layer.FindOrOpen(item.layer_identifier)

    def is_file_path_valid(self, path: str, layer: Sdf.Layer, log_error: bool = True) -> bool:
        """Check whether an asset path points to a readable file.

        Args:
            path: Asset path to inspect.
            layer: Layer the path is relative to.
            log_error: Whether validation failures should be logged.

        Returns:
            Whether the asset path is readable.
        """
        return self._repair_core.is_file_path_valid(layer.identifier, path, log_error=log_error)

    def was_the_asset_ingested(self, asset_path: str, ignore_invalid_paths: bool = True) -> bool:
        """Check whether an asset has valid ingestion metadata.

        Args:
            asset_path: Asset path to inspect.
            ignore_invalid_paths: Whether invalid paths should be treated as ingested.

        Returns:
            Whether the asset is ingested.
        """
        return self._repair_core.was_asset_ingested(asset_path, ignore_invalid_paths=ignore_invalid_paths)

    def asset_is_in_project_dir(self, asset_path: str, layer: Sdf.Layer, include_deps_dir: bool = False) -> bool:
        """Check whether an asset is inside the current project directory.

        Args:
            asset_path: Asset path to inspect.
            layer: Layer the path is relative to.
            include_deps_dir: Whether to count the project ``deps`` directory as a project path.

        Returns:
            Whether the asset is inside the project directory.
        """
        return self._repair_core.asset_is_in_project_dir(
            layer.identifier, asset_path, include_deps_dir=include_deps_dir
        )

    def is_replacement_asset_valid(self, item: PackagingErrorItem, asset_path: str) -> bool:
        """Check whether a replacement asset can be used for an error item.

        Args:
            item: The item being repaired.
            asset_path: Replacement asset path.

        Returns:
            Whether the asset is readable, ingested, and inside the project.
        """
        layer = self.get_layer(item)
        if layer is None:
            return False
        replacement_asset_type = AssetReplacementsValidators.get_replacement_asset_type(item.asset_path)
        return (
            self.is_file_path_valid(asset_path, layer, log_error=False)
            and (
                replacement_asset_type == ReplacementAssetType.TEXTURE
                or self.was_the_asset_ingested(asset_path, ignore_invalid_paths=False)
            )
            and self.asset_is_in_project_dir(asset_path, layer)
        )

    def __get_repair_requests(self, items: list[PackagingErrorItem] | None) -> list[PackagingRepairRequest]:
        return [self.__to_repair_request(item) for item in (items if items is not None else self._items)]

    @staticmethod
    def __to_repair_request(item: PackagingErrorItem) -> PackagingRepairRequest:
        return PackagingRepairRequest(
            layer_identifier=item.layer_identifier,
            prim_path=item.prim_path,
            asset_path=item.asset_path,
            fixed_asset_path=item.fixed_asset_path,
        )

    def get_item_children(self, item: PackagingErrorItem | None):
        """Get child items.

        Args:
            item: Parent item, or ``None`` for root items.

        Returns:
            The child items for the given item.
        """
        if item is None:
            return self._items
        return []

    def get_item_value_model_count(self, item: PackagingErrorItem | None):
        """Get the number of value columns for an item.

        Args:
            item: Item whose columns are requested.

        Returns:
            The number of value columns in the model.
        """
        return len(HEADER_DICT.keys())

    def subscribe_action_changed(self, callback: Callable[[], None]):
        """Subscribe to action-changed events.

        Args:
            callback: Callback invoked when an item's repair action changes.

        Returns:
            A subscription object that unsubscribes when destroyed.
        """
        return EventSubscription(self.__on_action_changed, callback)

    def destroy(self):
        """Destroy the model and clear subscriptions."""
        repair_core = self._repair_core
        self._repair_core = None
        if repair_core is not None:
            repair_core.destroy()
        reset_default_attrs(self)
