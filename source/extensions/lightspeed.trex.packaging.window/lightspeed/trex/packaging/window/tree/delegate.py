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

from __future__ import annotations

__all__ = ["PackagingErrorDelegate"]

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import omni.usd
from lightspeed.trex.utils.widget import accept_asset_if_valid_for_replacement, open_replacement_asset_file_picker
from omni import ui
from omni.flux.info_icon.widget import InfoIconWidget
from omni.flux.utils.common import Event, EventSubscription, reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl

if TYPE_CHECKING:
    from pxr import Sdf

from .item import PackagingActions, PackagingErrorItem
from .model import HEADER_DICT, PackagingErrorModel


class PackagingErrorDelegate(ui.AbstractItemDelegate):
    ROW_HEIGHT = ui.Pixel(24)
    ROW_PADDING = ui.Pixel(8)

    def __init__(self):
        super().__init__()

        self._default_attr = {
            "_PackagingErrorDelegate__on_file_picker_opened": None,
            "_PackagingErrorDelegate__on_file_picker_closed": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self.__on_file_picker_opened = Event()
        self.__on_file_picker_closed = Event()

    def build_widget(
        self, model: PackagingErrorModel, item: PackagingErrorItem, column_id: int, level: int, expanded: bool
    ):
        """Build a tree cell widget.

        Args:
            model: Packaging error model.
            item: Item represented by the cell.
            column_id: Column index to build.
            level: Tree indentation level.
            expanded: Whether the item is expanded.
        """
        if item is None:
            return
        with ui.HStack(spacing=self.ROW_PADDING, height=self.ROW_HEIGHT):
            ui.Spacer(width=0, height=0)
            if column_id == 0:
                ui.Label(
                    self._get_prim_path_display_name(item.prim_path), tooltip=str(item.prim_path), elided_text=True
                )
            if column_id == 1:
                ui.Label(
                    self._get_relative_path(item.asset_path, item.layer_identifier),
                    tooltip=self._get_asset_tooltip(item.asset_path, item.layer_identifier),
                    elided_text=True,
                )
            if column_id == 2:
                ui.Label(
                    self._get_relative_path(item.fixed_asset_path, item.layer_identifier),
                    tooltip=self._get_asset_tooltip(item.fixed_asset_path, item.layer_identifier),
                    elided_text=True,
                )
            if column_id == 3:
                with ui.HStack(spacing=self.ROW_PADDING):
                    action_combobox = ui.ComboBox(
                        list(PackagingActions).index(item.action),
                        *[action.value for action in PackagingActions],
                        identifier=f"packaging_action_combo_{OmniUrl(item.asset_path).stem}",
                    )
                    action_combobox.model.add_item_changed_fn(partial(self._on_action_changed, model, item))

                    with ui.VStack(width=0):
                        ui.Spacer(width=0)
                        InfoIconWidget(self._get_combobox_tooltip(item))
                        ui.Spacer(width=0)

                    ui.Spacer(width=0)

    def build_header(self, column_id: int):
        """Build a tree header cell.

        Args:
            column_id: Column index to build.
        """
        with ui.HStack(spacing=self.ROW_PADDING, height=self.ROW_HEIGHT):
            ui.Rectangle(name="ColumnSeparator", width=ui.Pixel(1))
            ui.Label(HEADER_DICT.get(column_id, ""))

    def _on_action_changed(
        self,
        model: PackagingErrorModel,
        item: PackagingErrorItem,
        combobox_model: ui.AbstractItemModel,
        _: ui.AbstractItem,
    ):
        """
        Callback triggered when the action combobox is changed.
        """
        action = list(PackagingActions)[combobox_model.get_item_value_model().get_value_as_int()]
        match action:
            case PackagingActions.IGNORE:
                model.reset_asset_paths([item])
            case PackagingActions.REPLACE_ASSET:
                self._update_reference(model, item)
            case PackagingActions.REMOVE_REFERENCE:
                model.remove_asset_paths([item])

    def _get_combobox_tooltip(self, item: PackagingErrorItem) -> str:
        """
        Args:
            item: The packaging error item.

        Returns:
            The tooltip for the packaging error item.
        """
        match item.action:
            case PackagingActions.IGNORE:
                return "The unresolved asset will be ignored when retrying the packaging process."
            case PackagingActions.REPLACE_ASSET:
                return "The unresolved asset reference will be replaced with the selected asset."
            case PackagingActions.REMOVE_REFERENCE:
                return "The unresolved asset reference will be removed from the mod."

        return "An action must be selected to fix the unresolved asset."

    def _get_prim_path_display_name(self, path: Sdf.Path) -> str:
        """
        Args:
            path: The prim path.

        Returns:
             The truncated display name for the prim path.
        """
        return (
            f".../{path.GetPrimPath().GetParentPath().name}/{path.GetPrimPath().name}/{path.name}"
            if path.IsPropertyPath()
            else f".../{path.GetParentPath().name}/{path.name}"
        )

    def _get_relative_path(self, asset_path: str | None, layer_identifier: str) -> str:
        """
        Args:
            asset_path: The asset path. If None, a pretty display name will be returned.
            layer_identifier: The layer identifier to use for the relative path.

        Returns:
            The relative path for the asset.
        """
        if asset_path is None:
            return "---"

        try:
            relative_path = Path(asset_path).relative_to(Path(layer_identifier).parent)
        except ValueError:
            relative_path = Path(asset_path)

        if relative_path.is_absolute():
            return relative_path.as_posix()
        return relative_path.as_posix() if str(relative_path).startswith(".") else f"./{relative_path.as_posix()}"

    def _get_asset_tooltip(self, asset_path: str | None, layer_identifier: str) -> str:
        """
        Args:
            asset_path: The asset path. If None, a description of the action will be returned.
            layer_identifier: The layer identifier to use for the tooltip.

        Returns:
            The tooltip for the asset.
        """
        if asset_path is None:
            return "The reference to the asset will be removed from the mod."
        return f"Absolute Path:  {asset_path}\nLayer Path:  {layer_identifier}"

    def _update_reference(self, model: PackagingErrorModel, item: PackagingErrorItem):
        """
        Open the file picker to select a new asset to replace the current asset.
        """
        current_file = item.asset_path if OmniUrl(item.asset_path).is_file else None

        self._on_file_picker_opened()
        open_replacement_asset_file_picker(
            f"Select a replacement asset for: {self._get_relative_path(item.asset_path, item.layer_identifier)}",
            item.asset_path,
            callback=partial(self._replace_asset_path, model, item),
            callback_cancel=lambda *_: self._cancel_file_picker(model, item),
            current_file=current_file,
        )

    def _replace_asset_path(self, model: PackagingErrorModel, item: PackagingErrorItem, file_path: str):
        """
        Replace the asset path with the selected file path and trigger the __on_file_picker_closed event.
        """
        layer = model.get_layer(item)
        if layer is None:
            model.reset_asset_paths([item])
            self._on_file_picker_closed()
            return
        if accept_asset_if_valid_for_replacement(
            file_path,
            layer,
            model,
            omni.usd.get_context(model.context_name),
            partial(self._accept_replacement_asset, model, item),
            ignore_ingestion_handler=partial(self._accept_replacement_asset, model, item),
            cancel_handler=partial(self._reset_replacement_asset, model, item),
        ):
            return

    def _accept_replacement_asset(self, model: PackagingErrorModel, item: PackagingErrorItem, file_path: str):
        model.replace_asset_paths({item: file_path})
        self._on_file_picker_closed()

    def _reset_replacement_asset(self, model: PackagingErrorModel, item: PackagingErrorItem):
        model.reset_asset_paths([item])
        self._on_file_picker_closed()

    def _cancel_file_picker(self, model: PackagingErrorModel, item: PackagingErrorItem):
        """
        Cancel the file picker action by resetting the asset path and triggering the __on_file_picker_closed event.
        """
        self._reset_replacement_asset(model, item)

    def _on_file_picker_opened(self):
        """
        Trigger the __on_file_picker_opened event
        """
        self.__on_file_picker_opened()

    def subscribe_file_picker_opened(self, function: Callable[[], None]):
        """Subscribe to file-picker opened events.

        Args:
            function: Callback invoked when the replacement file picker opens.

        Returns:
            A subscription object that unsubscribes when destroyed.
        """
        return EventSubscription(self.__on_file_picker_opened, function)

    def _on_file_picker_closed(self):
        """
        Trigger the __on_file_picker_closed event
        """
        self.__on_file_picker_closed()

    def subscribe_file_picker_closed(self, function: Callable[[], None]):
        """Subscribe to file-picker closed events.

        Args:
            function: Callback invoked when the replacement file picker closes.

        Returns:
            A subscription object that unsubscribes when destroyed.
        """
        return EventSubscription(self.__on_file_picker_closed, function)

    def destroy(self):
        """Destroy the delegate and clear subscriptions."""
        reset_default_attrs(self)
