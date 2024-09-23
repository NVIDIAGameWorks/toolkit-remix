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

from typing import Dict, List, Optional, Union

import omni.kit
import omni.ui as ui
import omni.usd
from omni.flux.property_widget_builder.model.usd import USDAttributeItem as _USDAttributeItem
from omni.flux.property_widget_builder.model.usd import USDDelegate as _USDPropertyDelegate
from omni.flux.property_widget_builder.model.usd import USDModel as _USDPropertyModel
from omni.flux.property_widget_builder.model.usd import USDPropertyWidget as _PropertyWidget
from omni.flux.property_widget_builder.model.usd import get_usd_listener_instance as _get_usd_listener_instance
from omni.flux.property_widget_builder.widget import FieldBuilder as _FieldBuilder
from omni.flux.property_widget_builder.widget import ItemGroup as _ItemGroup
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf


class PropertyWidget:
    def __init__(
        self,
        context_name: str,
        lookup_table: Dict[str, Dict[str, str]] = None,
        specific_attributes: List[str] = None,
        field_builders: list[_FieldBuilder] | None = None,
    ):
        """
        Property tree that show USD attributes

        Args:
            context_name: the usd context name
            lookup_table: table that will contain the display name of the attribute and the group. Example:
                {"inputs:diffuse_color_constant": {"name": "Base Color", "group": "Albedo"}}
            specific_attributes: list of exclusive attributes that we want to show
            field_builders (List[_FieldBuilder])
        """

        self._default_attr = {
            "_context_name": None,
            "_context": None,
            "_lookup_table": None,
            "_specific_attributes": None,
            "_root_frame": None,
            "_property_widget": None,
            "_property_model": None,
            "_property_delegate": None,
            "_paths": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self.__refresh_done = _Event()

        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)
        self._lookup_table = lookup_table or {}
        self._specific_attributes = specific_attributes

        self.__usd_listener_instance = _get_usd_listener_instance()

        self._paths = []
        self.__create_ui(field_builders=field_builders)

    def _refresh_done(self):
        """Call the event object that has the list of functions"""
        self.__refresh_done()

    def subscribe_refresh_done(self, callback):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__refresh_done, callback)

    @property
    def field_builders(self):
        if self._property_delegate is None:
            raise AttributeError("Need to run __create_ui first.")
        return self._property_delegate.field_builders

    def __create_ui(self, field_builders: list[_FieldBuilder] | None = None):
        self._property_model = _USDPropertyModel(self._context_name)
        self._property_delegate = _USDPropertyDelegate(field_builders=field_builders)
        self._root_frame = ui.Frame(height=0)
        with self._root_frame:
            self._property_widget = _PropertyWidget(
                self._context_name,
                model=self._property_model,
                delegate=self._property_delegate,
                refresh_callback=self.refresh,
            )

    def set_lookup_table(self, lookup_table: Dict[str, Dict[str, str]]):
        self._lookup_table = lookup_table

    def set_specific_attributes(self, specific_attributes: List[str]):
        self._specific_attributes = specific_attributes

    def refresh(self, paths: Optional[List[Union[str, "Sdf.Path"]]] = None):
        """
        Refresh the panel with the given prim paths

        Args:
            paths: the USD prim paths to use
        """
        if paths is not None:
            self._paths = paths

        if not self._root_frame or not self._root_frame.visible:
            return

        if self.__usd_listener_instance and self._property_model:  # noqa PLE0203
            self.__usd_listener_instance.remove_model(self._property_model)  # noqa PLE0203

        stage = self._context.get_stage()
        items = []
        valid_paths = []

        if stage is not None:
            prims = [stage.GetPrimAtPath(path) for path in self._paths]

            group_items = {}
            attrs_added = {}
            # pre-pass to check valid prims with the attribute
            for prim in prims:
                if not prim.IsValid():
                    continue
                valid_paths.append(prim.GetPath())
                attrs = prim.GetAttributes()
                for attr in attrs:
                    attr_name = attr.GetName()
                    if self._specific_attributes is not None and attr_name not in self._specific_attributes:
                        continue
                    attrs_added.setdefault(attr_name, []).append(attr)

            num_prims = len(valid_paths)
            if num_prims > 1:
                # TODO: Show that multiple items are selected!
                pass

            for attr_name, attrs in attrs_added.items():
                if 1 < len(attrs) != num_prims:
                    continue
                attr = attrs[0]

                display_attr_names = [attr_name]
                display_read_only = False
                display_name = attr.GetMetadata(Sdf.PropertySpec.DisplayNameKey)
                if display_name:
                    display_attr_names = [display_name]
                if attr_name in self._lookup_table:
                    display_attr_names = [self._lookup_table[attr_name]["name"]]
                    display_read_only = self._lookup_table[attr_name].get("read_only", False)

                attr_item = _USDAttributeItem(
                    self._context_name, [attr_.GetPath() for attr_ in attrs], read_only=display_read_only
                )

                # we don't need to repeat the attribute name multiple time here
                if attr_item.element_count != 1:
                    display_attr_names.extend([""] * (attr_item.element_count - 1))
                attr_item.set_display_attr_names(display_attr_names)

                attr_display_group = attr.GetDisplayGroup()
                group_name = None
                if attr_display_group and attr_name not in self._lookup_table:
                    group_name = attr_display_group
                # if this is in the lookup table, we override
                elif attr_name in self._lookup_table:
                    group_name = self._lookup_table[attr_name]["group"]

                if group_name is not None:
                    if group_name not in group_items:
                        group = _ItemGroup(group_name)
                        group_items[group_name] = group
                        items.append(group)
                    else:
                        group = group_items[group_name]
                    group.children.append(attr_item)
                else:
                    items.append(attr_item)

        self._property_model.set_prim_paths(valid_paths)
        self._property_model.set_items(items)
        self.__usd_listener_instance.add_model(self._property_model)
        self._refresh_done()

    @property
    def property_model(self):
        return self._property_model

    def show(self, value):
        """
        Show the panel or not

        Args:
            value: visible or not
        """
        if self._property_widget is not None:
            self._property_widget.enable_listeners(value)
        self._root_frame.visible = value
        if not value and self.__usd_listener_instance and self._property_model:
            self.__usd_listener_instance.remove_model(self._property_model)
        if not value:
            self._property_delegate.reset()

    @property
    def visible(self):
        return self._root_frame.visible

    def destroy(self):
        if self._root_frame:
            self._root_frame.clear()
        if self.__usd_listener_instance and self._property_model:
            self.__usd_listener_instance.remove_model(self._property_model)
        _reset_default_attrs(self)
        self.__usd_listener_instance = None
