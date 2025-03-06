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

from typing import List

import omni.ui as ui
import omni.usd
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.layer_manager.core.data_models import LayerType, LayerTypeKeys
from omni.flux.layer_tree.usd.widget import LayerModel as _LayerModel
from omni.flux.layer_tree.usd.widget import LayerTreeWidget as _LayerTreeWidget
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit.usd.layers import LayerUtils as _LayerUtils

from .packaging_tree.delegate import PackagingLayerDelegate as _PackagingLayerDelegate


class ModPackagingLayersWidget:
    _LAYER_TREE_HEIGHT = 160

    def __init__(self, context_name: str = ""):
        self._default_attr = {
            "_context_name": None,
            "_layer_core": None,
            "_layer_tree_model": None,
            "_item_changed_sub": None,
            "_checkbox_toggled_sub": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._layer_core = _LayerManagerCore(context_name=self._context_name)

        self.__layers_validity_changed = _Event()

        self.__create_ui()

    @property
    def packaged_layers(self) -> List[str]:
        """
        Get the list of layers to include in the packaged mod.
        """
        return [
            i.data["layer"].realPath
            for i in self._layer_tree_model.get_item_children(recursive=True)
            if i.data.get("package", False)
        ]

    def show(self, value: bool):
        """
        Show or hide this widget.
        This will trigger refreshes on show and will enable/disable listeners for the layer tree.
        """
        self._layer_tree_model.enable_listeners(value)
        if value:
            self._update_model_item_package_status()

    def __create_ui(self):
        with ui.ZStack():
            # Make sure to block all actions in the packaging tree
            self._layer_tree_model = _LayerModel(
                context_name=self._context_name,
                exclude_add_child_fn=self._get_all_layer_identifiers,
                exclude_remove_fn=self._get_all_layer_identifiers,
                exclude_lock_fn=self._get_all_layer_identifiers,
                exclude_move_fn=self._get_all_layer_identifiers,
                exclude_mute_fn=self._get_all_layer_identifiers,
                exclude_edit_target_fn=self._get_all_layer_identifiers,
            )
            self._item_changed_sub = self._layer_tree_model.subscribe_item_changed_fn(
                self._update_model_item_package_status
            )

            # Override the delegate
            delegate = _PackagingLayerDelegate()
            self._checkbox_toggled_sub = delegate.subscribe_checkbox_toggled(self._layers_validity_changed)

            _LayerTreeWidget(
                context_name=self._context_name,
                model=self._layer_tree_model,
                delegate=delegate,
                height=self._LAYER_TREE_HEIGHT,
                expansion_default=True,
                hide_create_insert_buttons=True,
            )

    def _update_model_item_package_status(self, *_):
        # Get the root mod layer
        replacement_layer = self._layer_core.get_layer(_LayerType.replacement)
        if not replacement_layer:
            return

        # Find the item corresponding with the mod layer
        replacement_item = self._layer_tree_model.find_item(
            replacement_layer.identifier, lambda i, v: i.data["layer"].identifier == v
        )
        if not replacement_item:
            return

        # Get all the root mod layers
        mod_layers = [
            replacement_item,
            *self._layer_tree_model.get_item_children(parent=replacement_item, recursive=True),
        ]

        # Make sure we only allow packaging sublayers of the root mod layer
        for item in self._layer_tree_model.get_item_children(recursive=True):
            is_capture_baker = (
                item.data["layer"].customLayerData.get(LayerTypeKeys.layer_type.value) == LayerType.capture_baker.value
            )
            # Force capture backer to be selected by excluding it from the UI and selecting it for packaging
            should_package = item in mod_layers and not is_capture_baker
            item.data["exclude_package"] = not should_package
            if "package" in item.data and should_package:
                continue
            # Set the default package status. Disable muted layers by default
            item.data["package"] = (
                (should_package or is_capture_baker) and item.data.get("visible") and item.data.get("parent_visible")
            )

        self._layers_validity_changed()

    def _get_all_layer_identifiers(self):
        context = omni.usd.get_context(self._context_name)
        if not context:
            return []
        stage = context.get_stage()
        if not stage:
            return []

        return _LayerUtils.get_all_sublayers(stage, include_session_layers=False, include_anonymous_layers=False)

    def _layers_validity_changed(self):
        """Call the event object"""
        self.__layers_validity_changed(
            any(i for i in self._layer_tree_model.get_item_children(recursive=True) if i.data.get("package", False))
        )

    def subscribe_layers_validity_changed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__layers_validity_changed, function)

    def destroy(self):
        _reset_default_attrs(self)
