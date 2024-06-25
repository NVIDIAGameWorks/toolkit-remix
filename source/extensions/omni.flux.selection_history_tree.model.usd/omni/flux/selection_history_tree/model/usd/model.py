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

from pathlib import Path
from typing import List

import omni.usd
from omni.flux.selection_history_tree.widget import SelectionHistoryModel as _SelectionHistoryModel
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .extension import get_usd_listener_instance as _get_usd_listener_instance
from .item_model import SelectionHistoryItem as _SelectionHistoryItem


class UsdSelectionHistoryModel(_SelectionHistoryModel):
    def __init__(self, context_name: str = ""):
        super().__init__()
        self._default_attr = {
            "_stage_event": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._usd_listener = _get_usd_listener_instance()  # don't reset it
        self.__block_list_selection = False
        self._context_name = context_name
        self._usd_context = omni.usd.get_context(context_name)
        self._stage = self._usd_context.get_stage()
        self._stage_event = None
        # the selection history should always be active, even when we don't see the widget
        self.enable_listeners(True)

    @property
    def stage(self):
        return self._stage

    def _block_list_selection(func):  # noqa N805
        def do(self, *args, **kwargs):  # noqa PLC0103
            self.__block_list_selection = True  # noqa PLW0212
            func(self, *args, **kwargs)  # noqa PLE1102

        return do

    def enable_listeners(self, value):
        """
        Enable USD listeners

        Args:
            value: True to enable, False to disable
        """
        if value:
            self._usd_listener.add_model(self)
            self._stage_event = self._usd_context.get_stage_event_stream().create_subscription_to_pop(
                self._on_stage_event, name="StageEvent"
            )
            self.__load_items_from_custom_layer_metadata()
        else:
            self._usd_listener.remove_model(self)
            self._stage_event = None

    @_block_list_selection
    def _set_active_items(self, items: List[_SelectionHistoryItem]):
        self._usd_context.get_selection().set_selected_prim_paths(
            [str(item.data.GetPath()) for item in items if item.is_valid()], True
        )

    def _get_active_items(self) -> List[str]:
        return list(set(self._usd_context.get_selection().get_selected_prim_paths()))

    def _on_stage_event(self, event):
        if event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            selection = self.get_active_items()
            self._on_stage_selection_changed(selection)
        elif event.type == int(omni.usd.StageEventType.OPENED):
            self.reset()

    def reset(self):
        """Reset the model"""
        # when we open stage, we delete the old stage listener, and re-add a new one
        self.enable_listeners(False)
        super().reset()
        self._stage = self._usd_context.get_stage()
        self.__load_items_from_custom_layer_metadata()
        self.enable_listeners(True)

    def _on_stage_selection_changed(self, current_selection):
        if self.__block_list_selection:
            self.__block_list_selection = False
            return
        stage = self._usd_context.get_stage()
        if not stage:
            return
        items = []
        for selection in current_selection:
            prim = stage.GetPrimAtPath(str(selection))
            if not prim.IsValid():
                continue
            items.insert(0, _SelectionHistoryItem(prim.GetName(), data=prim, tooltip=str(prim.GetPath())))
        if items:
            self.insert_items(items)
            self.__add_items_to_custom_layer()
        # TODO BUG REMIX-1278
        # self.set_active_items(items)
        self.__block_list_selection = False

    def __load_items_from_custom_layer_metadata(self):
        # Load Selection items from previous sessions if it exists
        stage = self._usd_context.get_stage()
        if not stage:
            return
        layer = stage.GetRootLayer()
        selection_history_dict = layer.customLayerData.get("SelectionHistoryList")
        if selection_history_dict:
            selection_history_dict_keys = list(selection_history_dict.keys())
            selection_history_dict_keys.sort(key=int, reverse=True)
            items = []
            for key in selection_history_dict_keys:
                cur_data = selection_history_dict[key]
                prim = stage.GetPrimAtPath(str(cur_data))
                items.append(_SelectionHistoryItem(Path(str(cur_data)).name, data=prim, tooltip=str(cur_data)))
            if items:
                self.insert_items(items)

    def __add_items_to_custom_layer(self):
        selection_history_dict = {}
        for index, item in enumerate(self.get_item_children(None)):
            selection_history_dict.update({str(index): str(item.data.GetPath())})
        # Add current list items to custom layer data
        stage = self._usd_context.get_stage()
        layer = stage.GetRootLayer()
        current_data = layer.customLayerData
        current_data.update({"SelectionHistoryList": selection_history_dict})
        layer.customLayerData = current_data

    def destroy(self):
        self.enable_listeners(False)
        self._usd_listener = None
        _reset_default_attrs(self)
