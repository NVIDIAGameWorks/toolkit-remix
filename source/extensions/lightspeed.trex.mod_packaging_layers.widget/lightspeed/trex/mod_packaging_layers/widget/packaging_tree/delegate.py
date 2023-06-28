"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from functools import partial

import omni.ui as ui
from omni.flux.layer_tree.usd.widget import LayerDelegate as _LayerDelegate
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class PackagingLayerDelegate(_LayerDelegate):
    __DEFAULT_IMAGE_ICON_SIZE = 24

    def __init__(self):
        super().__init__()

        self._default_attr.update(
            {
                "_checkbox_widgets": None,
            }
        )
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._initialize_gradient_styles()
        self._initialize_internal_members()

        self._checkbox_widgets = {}

        self.__checkbox_toggled = _Event()

    def _build_widget_icons(self, _):
        pass

    def _build_branch_start_icons(self, item):
        with ui.VStack(width=self.__DEFAULT_IMAGE_ICON_SIZE):
            ui.Spacer()
            checkbox = ui.CheckBox(
                height=0, enabled=not item.data.get("exclude_package", False), identifier="select_layer"
            )
            checkbox.model.set_value(item.data.get("package", False))  # Might not exist
            checkbox.model.add_value_changed_fn(partial(self._on_enabled_changed, item))
            self._checkbox_widgets[item.data["layer"].identifier if item.data["layer"] else None] = checkbox
            ui.Spacer()

    def _on_enabled_changed(self, item, model):
        def update_children_recursive(parent, value):
            for child in parent.children:
                child.data["package"] = value
                self._checkbox_widgets[child.data["layer"].identifier].model.set_value(value)
                update_children_recursive(child, value)

        item.data["package"] = model.get_value_as_bool()
        update_children_recursive(item, model.get_value_as_bool())
        self._checkbox_toggled()

    def _checkbox_toggled(self):
        """Call the event object"""
        self.__checkbox_toggled()

    def subscribe_checkbox_toggled(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__checkbox_toggled, function)

    def destroy(self):
        _reset_default_attrs(self)
