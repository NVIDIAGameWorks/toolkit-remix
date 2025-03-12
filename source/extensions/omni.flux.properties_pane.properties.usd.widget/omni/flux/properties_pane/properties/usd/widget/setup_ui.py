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

from typing import Callable, Dict, List, Optional, Union

import omni.kit
import omni.ui as ui
import omni.usd
from omni.flux.property_widget_builder.model.usd import USDAttributeDef as _USDAttributeDef
from omni.flux.property_widget_builder.model.usd import USDAttributeItem as _USDAttributeItem
from omni.flux.property_widget_builder.model.usd import USDDelegate as _USDPropertyDelegate
from omni.flux.property_widget_builder.model.usd import USDModel as _USDPropertyModel
from omni.flux.property_widget_builder.model.usd import USDPropertyWidget as _PropertyWidget
from omni.flux.property_widget_builder.model.usd import VirtualUSDAttributeItem as _VirtualUSDAttributeItem
from omni.flux.property_widget_builder.model.usd import get_usd_listener_instance as _get_usd_listener_instance
from omni.flux.property_widget_builder.widget import FieldBuilder as _FieldBuilder
from omni.flux.property_widget_builder.widget import ItemGroup as _ItemGroup
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf, Usd


class PropertyWidget:
    def __init__(
        self,
        context_name: str,
        lookup_table: Dict[str, Dict[str, str]] = None,
        specific_attributes: List[str] = None,
        field_builders: list[_FieldBuilder] | None = None,
        optional_attributes: list[tuple[Callable[[Usd.Prim], bool], Dict[str, any]]] = None,
        tree_column_widths: List[ui.Length] = None,
        columns_resizable: bool = False,
        right_aligned_labels: bool = True,
    ):
        """
        Property tree that show USD attributes

        Args:
            context_name: the usd context name
            lookup_table: table that will contain the display name of the attribute and the group. Example:
                {"inputs:diffuse_color_constant": {"name": "Base Color", "group": "Albedo"}}
            specific_attributes: list of exclusive attributes that we want to show
            field_builders (List[_FieldBuilder])
            optional_attributes: extra attributes that can be created on light prims.
                List of (test_func, dictionary) Tuples.
                Test_func takes a prim and returns a bool,
                Dictionaries should contain name, token, type, and default value.
            tree_column_widths: the width of the columns
            columns_resizable: if the columns are resizable
            right_aligned_labels: if the labels are right aligned
        """

        self._default_attr = {
            "_context_name": None,
            "_context": None,
            "_lookup_table": None,
            "_specific_attributes": None,
            "_root_frame": None,
            "_optional_attributes": None,
            "_tree_column_widths": None,
            "_columns_resizable": None,
            "_right_aligned_labels": None,
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
        self._optional_attributes = optional_attributes
        self._tree_column_widths = tree_column_widths
        self._columns_resizable = columns_resizable
        self._right_aligned_labels = right_aligned_labels

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
        self._property_delegate = _USDPropertyDelegate(
            field_builders=field_builders, right_aligned_labels=self._right_aligned_labels
        )
        self._root_frame = ui.Frame(height=0)
        with self._root_frame:
            self._property_widget = _PropertyWidget(
                self._context_name,
                model=self._property_model,
                delegate=self._property_delegate,
                refresh_callback=self.refresh,
                tree_column_widths=self._tree_column_widths,
                columns_resizable=self._columns_resizable,
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
        items: list[_USDAttributeItem | _VirtualUSDAttributeItem | _ItemGroup] = []
        valid_paths = []

        if stage is not None:
            prims = [stage.GetPrimAtPath(path) for path in self._paths]

            group_items = {}
            attrs_added: dict[str, list[Usd.Attribute | _USDAttributeDef]] = {}
            optional_attribute_names = {
                attr_dict["token"] for test_func, attr_dict in (self._optional_attributes or [])
            }
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
                    if self._optional_attributes is not None and attr_name in optional_attribute_names:
                        continue  # skip, we will handle optional attributes in the next loop
                    attrs_added.setdefault(attr_name, []).append(attr)

                if self._optional_attributes is not None:
                    for test_func, attr_dict in self._optional_attributes:
                        attr_name = attr_dict["token"]
                        if test_func(prim):
                            attr_def = _USDAttributeDef(
                                path=prim.GetPath().AppendProperty(attr_dict["token"]),
                                attr_type=attr_dict["type"],
                                value=attr_dict["default_value"],
                                documentation=attr_dict.get("documentation"),
                                display_group=attr_dict.get("display_group"),
                            )
                            attrs_added.setdefault(attr_name, []).append(attr_def)

            num_prims = len(valid_paths)
            if num_prims > 1:
                # TODO: Show that multiple items are selected!
                pass

            for attr_name, attrs in attrs_added.items():
                if 1 < len(attrs) != num_prims:
                    continue

                attr = attrs[0]

                display_name = None
                if isinstance(attr, Usd.Attribute):
                    attribute_metadata_docs = attr.GetMetadata(Sdf.PropertySpec.DocumentationKey)
                    display_name = attr.GetMetadata(Sdf.PropertySpec.DisplayNameKey)
                    group_name = attr.GetDisplayGroup()
                elif isinstance(attr, _USDAttributeDef):
                    attribute_metadata_docs = attr.documentation
                    group_name = attr.display_group
                else:
                    raise ValueError("Invalid type.")

                display_attr_names = [attr_name]
                if display_name:
                    display_attr_names = [display_name]
                display_read_only = False
                if attr_name in self._lookup_table:
                    display_attr_names = [self._lookup_table[attr_name]["name"]]
                    display_read_only = self._lookup_table[attr_name].get("read_only", False)
                    group_name = self._lookup_table[attr_name].get("group")

                display_attr_names_tooltips = [attr_name]
                if attribute_metadata_docs is not None:
                    documentation = attr_name + ":\n" + attribute_metadata_docs
                    if documentation:
                        display_attr_names_tooltips = [documentation]

                if isinstance(attr, Usd.Attribute):
                    attr_item = _USDAttributeItem(
                        self._context_name,
                        [attr_.GetPath() for attr_ in attrs],
                        read_only=display_read_only,
                        display_attr_names=display_attr_names,
                        display_attr_names_tooltip=display_attr_names_tooltips,
                    )
                elif isinstance(attr, _USDAttributeDef):
                    attr_item = _VirtualUSDAttributeItem(
                        self._context_name,
                        [attr_def_.path for attr_def_ in attrs],
                        value_type_name=attr.attr_type,
                        default_value=attr.value,
                        read_only=display_read_only,
                        display_attr_names=display_attr_names,
                        display_attr_names_tooltip=display_attr_names_tooltips,
                    )
                else:
                    raise ValueError("Invalid type.")

                if group_name:
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
