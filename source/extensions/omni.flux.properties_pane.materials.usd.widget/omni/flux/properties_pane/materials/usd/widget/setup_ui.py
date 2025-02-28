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

import asyncio
from typing import Dict, List, Optional, Union

import omni.kit
import omni.kit.material.library
import omni.ui as ui
import omni.usd
from omni.flux.material_api import ShaderInfoAPI
from omni.flux.property_widget_builder.model.usd import DisableAllListenersBlock as _USDDisableAllListenersBlock
from omni.flux.property_widget_builder.model.usd import USDDelegate as _USDPropertyDelegate
from omni.flux.property_widget_builder.model.usd import USDMetadataListItem as _USDMetadataListItem
from omni.flux.property_widget_builder.model.usd import USDModel as _USDPropertyModel
from omni.flux.property_widget_builder.model.usd import USDPropertyWidget as _PropertyWidget
from omni.flux.property_widget_builder.model.usd import VirtualUSDAttributeItem as _VirtualUSDAttributeItem
from omni.flux.property_widget_builder.model.usd import VirtualUSDAttrListItem as _VirtualUSDAttrListItem
from omni.flux.property_widget_builder.model.usd import get_usd_listener_instance as _get_usd_listener_instance
from omni.flux.property_widget_builder.widget import FieldBuilder as _FieldBuilder
from omni.flux.property_widget_builder.widget import ItemGroup as _ItemGroup
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf, Usd, UsdShade, Vt

from .lookup_table import LOOKUP_TABLE

SHADER_ATTR_IGNORE_LIST = [
    "outputs:out",
    "info:id",
    "info:implementationSource",
    "info:mdl:sourceAsset",
    "info:mdl:sourceAsset:subIdentifier",
    "ui:displayName",
    "inputs:v",
]


class MaterialPropertyWidget:
    def __init__(
        self,
        context_name: str,
        tree_column_widths: Optional[List[ui.Length]] = None,
        lookup_table: Optional[Dict[str, Dict[str, str]]] = None,
        create_color_space_attributes: bool = True,
        field_builders: list[_FieldBuilder] | None = None,
    ):
        """
        Args:
            context_name (str)
            tree_column_widths (Optional[List[ui.Length]])
            lookup_table (Optional[Dict[str, Dict[str, str]]]): Table used to override display name or group for
                attributes.
            create_color_space_attributes (bool)
            field_builders (List[_FieldBuilder])
        """

        self._default_attr = {
            "_context": None,
            "_root_frame": None,
            "_property_widget": None,
            "_property_model": None,
            "_property_delegate": None,
            "_tree_column_widths": None,
            "_lookup_table": None,
            "_paths": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self.__refresh_done = _Event()

        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)
        self._tree_column_widths = tree_column_widths

        self.__usd_listener_instance = _get_usd_listener_instance()

        self._paths = []
        self._lookup_table = lookup_table or LOOKUP_TABLE

        self._create_color_space_attributes = create_color_space_attributes

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
        self._root_frame = ui.Frame()
        with self._root_frame:
            self._property_widget = _PropertyWidget(
                self._context_name,
                model=self._property_model,
                delegate=self._property_delegate,
                tree_column_widths=self._tree_column_widths,
                refresh_callback=self.refresh,
            )

    def refresh(self, paths: Optional[List[Union[str, "Sdf.Path"]]] = None):
        """
        Refresh the panel with the given prim paths

        Args:
            paths: the USD prim paths to use
        """
        asyncio.ensure_future(self._deferred_refresh(paths))

    @omni.usd.handle_exception
    async def _deferred_refresh(self, paths: Optional[List[Union[str, "Sdf.Path"]]] = None):
        """
        Deferred because we need to handle attribute(s) generated on fly by the mdl

        Args:
            paths: the paths of material
        """
        if paths is not None:
            self._paths = paths

        # Wait 1 frame to make sure the USD it up-to-date
        await omni.kit.app.get_app().next_update_async()

        if not self._root_frame or not self._root_frame.visible:
            return

        if self.__usd_listener_instance and self._property_model:  # noqa PLE0203
            self.__usd_listener_instance.remove_model(self._property_model)  # noqa PLE0203

        stage = self._context.get_stage()
        items = []
        valid_paths = []

        if stage is not None:  # noqa PLR1702
            prims = [stage.GetPrimAtPath(path) for path in self._paths]

            shader_paths = []
            # relative attr name to item
            attr_added: dict[str, list[tuple[Usd.Prim, Usd.Attribute]]] = {}

            with _USDDisableAllListenersBlock(self.__usd_listener_instance):
                for prim in prims:
                    if not prim.IsValid():
                        continue
                    # if this is not a material, skip
                    if not prim.IsA(UsdShade.Material):
                        continue
                    # grab shader prims
                    shader_prim = omni.usd.get_shader_from_material(prim, True)
                    if shader_prim:
                        shader_paths.append(shader_prim.GetPath())

                        # iterate over input parameters defined in mdls as well as attributes:
                        for shader_attr in ShaderInfoAPI(shader_prim).get_input_properties():
                            if shader_attr.IsHidden():
                                continue
                            attr_name = shader_attr.GetName()
                            # check if shader attribute already exists in material
                            material_attr = prim.GetAttribute(attr_name)
                            if material_attr.IsHidden():
                                continue
                            if material_attr:
                                # use material attribute NOT shader attribute
                                attr_added.setdefault(attr_name, []).append((shader_prim, material_attr))
                                continue

                            if any(ignore_name in attr_name for ignore_name in SHADER_ATTR_IGNORE_LIST):
                                continue

                            # add paths to usd_changed watch list
                            prim_path = shader_prim.GetPath()
                            if prim_path not in valid_paths:
                                valid_paths.append(prim_path)

                            attr_added.setdefault(attr_name, []).append((shader_prim, shader_attr))

                        # add source color space
                        shader = UsdShade.Shader(shader_prim)
                        if shader.GetShaderId() == "UsdUVTexture":
                            attr_name = "inputs:sourceColorSpace"
                            attr_mat = prim.GetAttribute(attr_name)
                            attr_shader = shader.GetAttribute(attr_name)
                            if not attr_mat and not attr_shader:
                                type_name = Sdf.ValueTypeNames.Find("token")
                                attr_mat = shader.CreateInput("sourceColorSpace", type_name).GetAttr()
                                attr_mat.SetMetadata("allowedTokens", Vt.TokenArray(3, ("auto", "raw", "sRGB")))
                                attr_mat.Set("auto")
                            elif attr_mat.GetTypeName() == Sdf.ValueTypeNames.Token:
                                tokens = attr_mat.GetMetadata("allowedTokens")
                                if not tokens:
                                    # fix missing tokens on attribute
                                    attr_mat.SetMetadata("allowedTokens", ["auto", "raw", "sRGB"])
                            attr_added.setdefault(attr_name, []).append((shader_prim, attr_mat))

                        valid_paths.append(shader_prim.GetPath())

                    valid_paths.append(prim.GetPath())

                group_items = {}
                num_prims = len(prims)
                for attr_name, prims_and_placeholders in attr_added.items():
                    # Only allow editing common attributes
                    if 1 < num_prims != len(prims_and_placeholders):
                        # skipping attribute because not all prims have it
                        continue
                    attributes = [
                        shader_prim_.GetAttribute(attr_.GetName()) for shader_prim_, attr_ in prims_and_placeholders
                    ]
                    attribute_paths = [attr_.GetPath() for attr_ in attributes]

                    shader_prim, placeholder = prims_and_placeholders[0]
                    attr_name = placeholder.GetName()
                    display_attr_names = [attr_name]

                    display_name = placeholder.GetMetadata(Sdf.PropertySpec.DisplayNameKey)
                    if display_name:
                        display_attr_names = [display_name]
                    if attr_name in self._lookup_table:
                        display_attr_names = [self._lookup_table[attr_name]["name"]]

                    # description
                    description = "No description"
                    metadata = placeholder.GetAllMetadata()
                    if metadata and metadata.get("documentation"):
                        description = metadata.get("documentation", description)
                    descriptions = [description]

                    sdr_metadata = placeholder.GetMetadata("sdrMetadata")
                    if sdr_metadata and sdr_metadata.get("options"):
                        options: list[tuple[str, int]] = sdr_metadata.get("options")
                        if isinstance(options, list):
                            # ex: [('wrap_clamp', 0), ('wrap_repeat', 1), ('wrap_mirrored_repeat', 2), ('wrap_clip', 3)]
                            str_options = [name for name, _index in options]
                        elif isinstance(options, str):
                            # ex: 'mono_alpha:0|mono_average:1|mono_luminance:2|mono_maximum:3'
                            str_options = [name_and_index.split(":")[0] for name_and_index in options.split("|")]
                        else:
                            raise ValueError(f"Invalid sdrMetadata options type: {type(options)}")
                        default_value = placeholder.GetDefaultValue()
                        str_default = str_options[default_value]
                        attr_item = _VirtualUSDAttrListItem(
                            self._context_name,
                            attribute_paths,
                            str_default,
                            str_options,
                            value_type_name=placeholder.GetTypeName(),
                            metadata=placeholder.GetAllMetadata(),
                            display_attr_names=display_attr_names,
                            display_attr_names_tooltip=descriptions,
                        )
                    else:
                        attr_item = _VirtualUSDAttributeItem(
                            self._context_name,
                            attribute_paths,
                            value_type_name=placeholder.GetTypeName(),
                            default_value=placeholder.GetDefaultValue(),
                            metadata=placeholder.GetAllMetadata(),
                            display_attr_names=display_attr_names,
                            display_attr_names_tooltip=descriptions,
                        )

                    attr_display_group = placeholder.GetDisplayGroup()
                    attr_name_lower = attr_name.lower()
                    if attr_display_group:
                        group_name = attr_display_group.removeprefix(UsdShade.Tokens.inputs.capitalize())
                    # if this is in the lookup table, we override
                    elif attr_name in self._lookup_table:
                        group_name = self._lookup_table[attr_name]["group"]
                    elif attr_name_lower.startswith("inputs"):
                        group_name = "Inputs"
                    elif attr_name_lower.startswith("output"):
                        group_name = "Outputs"
                    else:
                        group_name = "Other"

                    # texture attribute will get color space attribute
                    color_space_item = None
                    if self._create_color_space_attributes:
                        color_space_metadata = placeholder.GetMetadata("colorSpace")
                        if color_space_metadata:
                            # this is a texture
                            # TODO: Add Support for metadata item when attr does not exist yet.
                            color_space_item = _USDMetadataListItem(
                                self._context_name,
                                attribute_paths,
                                "auto",
                                ["auto", "raw", "sRGB"],
                                display_attr_names=display_attr_names,
                                display_attr_names_tooltip=descriptions,
                                metadata_key="colorSpace",
                            )

                    if group_name is not None:
                        if group_name not in group_items:
                            group = _ItemGroup(group_name)
                            group_items[group_name] = group
                            items.append(group)
                        else:
                            group = group_items[group_name]
                        group.children.append(attr_item)
                        if color_space_item:
                            group.children.append(color_space_item)
                    else:
                        items.append(attr_item)
                        if color_space_item:
                            items.append(color_space_item)

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

    def destroy(self):
        if self._root_frame:
            self._root_frame.clear()
        if self.__usd_listener_instance and self._property_model:
            self.__usd_listener_instance.remove_model(self._property_model)
        _reset_default_attrs(self)
        self.__usd_listener_instance = None
