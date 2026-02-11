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

__all__ = ["HEADER_DICT", "AssetValidationError", "PackagingErrorModel"]

from collections.abc import Callable
from enum import Enum
from typing import Any

import omni.kit.undo
from lightspeed.common.constants import USD_EXTENSIONS
from lightspeed.trex.asset_replacements.core.shared import Setup as AssetReplacementsCore
from lightspeed.trex.texture_replacements.core.shared import TextureReplacementsCore
from lightspeed.trex.utils.common.file_utils import is_usd_file_path_valid_for_filepicker
from omni import ui
from omni.flux.utils.common import Event, EventSubscription, reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl
from pxr import Sdf, Usd

from .item import PackagingActions, PackagingErrorItem

HEADER_DICT = {0: "Prim Path", 1: "Unresolved Path", 2: "Updated Path", 3: "Action"}


class AssetValidationError(Enum):
    """
    Enum for the different types of asset validation errors.
    """

    NONE = 0
    INVALID_REFERENCE = 1
    INVALID_TEXTURE = 2
    NOT_INGESTED = 3
    NOT_IN_PROJECT = 4


class PackagingErrorModel(ui.AbstractItemModel):
    def __init__(self, context_name: str = ""):
        super().__init__()

        self.default_attr = {
            "_context_name": [],
            "_items": [],
            "_asset_core": [],
            "_texture_core": [],
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._items = []

        self._asset_core = AssetReplacementsCore(context_name=context_name)
        self._texture_core = TextureReplacementsCore(context_name=context_name)

        self.__on_action_changed = Event()

    def refresh(self, unresolved_assets: list[tuple[str, str, str]]):
        """
        Refresh the model with a new list of unresolved assets

        Args:
            unresolved_assets: A list of tuples containing the layer, prim path, and asset path of the unresolved assets
        """
        self._items = [PackagingErrorItem(layer, path, asset) for layer, path, asset in unresolved_assets]
        self._item_changed(None)

    def replace_asset_paths(self, items: dict[PackagingErrorItem, str]):
        """
        Replace the asset paths for the given items with the given new paths

        Args:
            items: A dictionary of items and their new paths
        """
        for item, new_path in items.items():
            item.fixed_asset_path = new_path
        self.__on_action_changed()

    def remove_asset_paths(self, items: list[PackagingErrorItem]):
        """
        Remove the fixed asset paths for the given items
        """
        for item in items:
            item.fixed_asset_path = None
        self.__on_action_changed()

    def reset_asset_paths(self, items: list[PackagingErrorItem]):
        """
        Reset the fixed asset paths for the given items to the original asset paths
        """
        for item in items or self._items:
            item.fixed_asset_path = item.asset_path
        self.__on_action_changed()

    def apply_new_paths(self, items: list[PackagingErrorItem] | None = None) -> list:
        """
        Apply the fixed asset paths for the given items
        """
        ignored_items = []

        stage = omni.usd.get_context(self._context_name).get_stage()

        with omni.kit.undo.group():
            for item in items or self._items:
                is_reference = OmniUrl(item.asset_path).suffix in USD_EXTENSIONS
                target_layer = Sdf.Layer.FindOrOpen(item.layer_identifier)

                if item.action == PackagingActions.IGNORE:
                    ignored_items.append((item.layer_identifier, str(item.prim_path), item.asset_path))
                    continue

                with Usd.EditContext(stage, target_layer):
                    if item.action == PackagingActions.REPLACE_ASSET:
                        if is_reference:
                            self._asset_core.remove_reference(
                                stage,
                                item.prim_path,
                                Sdf.Reference(assetPath=item.asset_path, primPath=item.prim_path),
                                target_layer,
                            )
                            self._asset_core.add_new_reference(
                                stage,
                                item.prim_path,
                                item.fixed_asset_path,
                                self._asset_core.get_ref_default_prim_tag(),
                                target_layer,
                            )
                        else:
                            self._texture_core.replace_textures(
                                [(str(item.prim_path), item.fixed_asset_path)], use_undo_group=False
                            )
                    elif is_reference:
                        self._asset_core.remove_reference(
                            stage,
                            item.prim_path,
                            Sdf.Reference(assetPath=item.asset_path, primPath=item.prim_path),
                            target_layer,
                        )
                    else:
                        self._texture_core.replace_textures(
                            [(str(item.prim_path), None)], force=True, use_undo_group=False
                        )

        self.__on_action_changed()

        return ignored_items

    def validate_selected_path(
        self, item: PackagingErrorItem, is_reference: bool, directory: str, filename: str
    ) -> AssetValidationError:
        """
        Validate the selected asset path.

        Args:
            item: The item to validate the path for
            is_reference: Whether the asset is a reference or a texture
            directory: The directory of the selected asset path
            filename: The filename of the selected asset path
        """
        asset_url = OmniUrl(directory) / filename

        if is_reference:
            if not is_usd_file_path_valid_for_filepicker(directory, filename):
                return AssetValidationError.INVALID_REFERENCE
        elif asset_url.suffix.lower() != ".dds":
            return AssetValidationError.INVALID_TEXTURE

        if not self._asset_core.was_the_asset_ingested(str(asset_url)):
            return AssetValidationError.NOT_INGESTED

        if not self._asset_core.asset_is_in_project_dir(
            str(asset_url), layer=Sdf.Layer.FindOrOpen(item.layer_identifier)
        ):
            return AssetValidationError.NOT_IN_PROJECT

        return AssetValidationError.NONE

    def get_item_children(self, item: PackagingErrorItem | None):
        """
        Return the children of the given item
        """
        if item is None:
            return self._items
        return []

    def get_item_value_model_count(self, item: PackagingErrorItem | None):
        """
        Return the number of columns in the model
        """
        return len(HEADER_DICT.keys())

    def subscribe_action_changed(self, callback: Callable[[], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return EventSubscription(self.__on_action_changed, callback)

    def destroy(self):
        reset_default_attrs(self)
