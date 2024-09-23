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
from omni.flux.property_widget_builder.model.usd import DisableAllListenersBlock as _USDDisableAllListenersBlock
from omni.flux.property_widget_builder.model.usd import USDAttributeItem as _USDAttributeItem
from omni.flux.property_widget_builder.model.usd import USDAttrListItem as _USDAttrListItem
from omni.flux.property_widget_builder.model.usd import USDDelegate as _USDPropertyDelegate
from omni.flux.property_widget_builder.model.usd import USDMetadataListItem as _USDMetadataListItem
from omni.flux.property_widget_builder.model.usd import USDModel as _USDPropertyModel
from omni.flux.property_widget_builder.model.usd import USDPropertyWidget as _PropertyWidget
from omni.flux.property_widget_builder.model.usd import get_usd_listener_instance as _get_usd_listener_instance
from omni.flux.property_widget_builder.widget import FieldBuilder as _FieldBuilder
from omni.flux.property_widget_builder.widget import ItemGroup as _ItemGroup
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf, UsdShade, Vt

from .lookup_table import LOOKUP_TABLE


@omni.usd.handle_exception
async def _load_mdl_parameters_for_prim_async(context, prim, recreate=True):
    """
    Alternative to `Context.load_mdl_parameters_for_prim_async` which allows the `recreate` kwarg to be provided.
    """
    path = prim.GetPath().pathString
    stage_future = asyncio.Future()

    if context.add_to_pending_creating_mdl_paths(path, recreate=recreate):

        def on_stage(stage_event):
            if stage_event.payload["prim_path"] == path and not stage_future.done():
                stage_future.set_result(True)

        stage_sub = context.get_stage_event_stream().create_subscription_to_pop_by_type(  # noqa: PLW0612, F841
            int(omni.usd.StageEventType.MDL_PARAM_LOADED), on_stage, name="load_mdl_parameters_for_prim"
        )
        await stage_future


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

        def loaded_mdl_subids(mtl_list, filename):
            mdl_dict = {}
            for mtl in mtl_list:
                mdl_dict[mtl.name] = mtl.annotations

            material_annotations[filename] = mdl_dict

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
            mtl_paths = []
            material_annotations = {}
            # relative attr name to item
            attr_added: dict[str, list[_USDAttributeItem]] = {}

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

                        # grab mdls paths
                        shader = UsdShade.Shader(shader_prim if shader_prim else prim)
                        asset = shader.GetSourceAsset("mdl") if shader else None
                        mdl_file = asset.resolvedPath if asset else None
                        if mdl_file:
                            mtl_paths.append(mdl_file)
                            await omni.kit.material.library.get_subidentifier_from_mdl(
                                mdl_file=mdl_file,
                                on_complete_fn=lambda l, f=mdl_file: loaded_mdl_subids(mtl_list=l, filename=f),
                            )

                        # load the mdl parameters
                        ignore_list = [
                            "outputs:out",
                            "info:id",
                            "info:implementationSource",
                            "info:mdl:sourceAsset",
                            "info:mdl:sourceAsset:subIdentifier",
                            "ui:displayName",
                            "inputs:v",
                        ]

                        # TODO Bug OM-76692 - Causes "reorder properties" attribute to be added on viewport selection
                        await _load_mdl_parameters_for_prim_async(self._context, shader_prim, recreate=True)

                        # get child attributes
                        for shader_attr in shader_prim.GetAttributes():
                            if shader_attr.IsHidden():
                                continue
                            attr_name = shader_attr.GetName()
                            # check if shader attribute already exists in material
                            material_attr = prim.GetAttribute(attr_name)
                            if material_attr.IsHidden():
                                continue
                            if material_attr:
                                # use material attribute NOT shader attribute
                                attr_added.setdefault(attr_name, []).append(material_attr)
                                continue

                            # add paths to usd_changed watch list
                            prim_path = shader_attr.GetPrimPath()
                            if prim_path not in valid_paths:
                                valid_paths.append(prim_path)

                            if not any(name in shader_attr.GetName() for name in ignore_list):
                                attr_added.setdefault(attr_name, []).append(shader_attr)

                        # add source color space
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
                            attr_added.setdefault(attr_name, []).append(attr_mat)

                        valid_paths.append(shader_prim.GetPath())

                    valid_paths.append(prim.GetPath())

                group_items = {}
                num_prims = len(prims)
                for attr_name, attrs in attr_added.items():
                    # Only allow editing common attributes
                    if 1 < num_prims != len(attrs):
                        # skipping attribute because not all prims have it
                        continue
                    attr = attrs[0]
                    attr_name = attr.GetName()
                    display_attr_names = [attr_name]
                    attribute_paths = [attr_.GetPath() for attr_ in attrs]
                    display_name = attr.GetMetadata(Sdf.PropertySpec.DisplayNameKey)
                    if display_name:
                        display_attr_names = [display_name]
                    if attr_name in self._lookup_table:
                        display_attr_names = [self._lookup_table[attr_name]["name"]]

                    # description
                    shade_input = UsdShade.Input(attr)
                    description = "No description"
                    metadata = attr.GetAllMetadata()
                    if shade_input and metadata.get("documentation"):
                        description = metadata.get("documentation", description)
                    descriptions = [description]

                    if shade_input and shade_input.HasRenderType() and shade_input.HasSdrMetadataByKey("options"):
                        options = shade_input.GetSdrMetadataByKey("options").split("|")

                        # This is not the standard USD way to get default. The
                        # standard way is Sdr. But out shader compiler produces
                        # this metadata in the session layer, so it will be
                        # working for MDL
                        custom = attr.GetCustomData()
                        default_value = custom.get("default", 0)

                        str_options = [option.split(":")[0] for option in options]
                        attr_item = _USDAttrListItem(
                            self._context_name,
                            attribute_paths,
                            None,
                            str_options[default_value],
                            str_options,
                            display_attr_names=display_attr_names,
                            display_attr_names_tooltip=descriptions,
                        )
                    else:
                        attr_item = _USDAttributeItem(self._context_name, attribute_paths)
                        # we don't need to repeat the attribute name multiple time here
                        if attr_item.element_count != 1:
                            display_attr_names.extend([""] * (attr_item.element_count - 1))
                            descriptions.extend([""] * (attr_item.element_count - 1))
                        attr_item.set_display_attr_names(display_attr_names)
                        attr_item.set_display_attr_names_tooltip(descriptions)

                    attr_display_group = attr.GetDisplayGroup()
                    if attr_display_group:
                        group_name = attr_display_group
                    # if this is in the lookup table, we override
                    elif attr_name in self._lookup_table:
                        group_name = self._lookup_table[attr_name]["group"]
                    elif attr_name.startswith("inputs"):
                        group_name = "Inputs"
                    elif attr_name.startswith("output"):
                        group_name = "Outputs"
                    else:
                        group_name = "Other"

                    # texture attribute will get color space attribute
                    color_space_item = None
                    if self._create_color_space_attributes:
                        color_space_metadata = attr.GetMetadata("colorSpace")
                        if color_space_metadata:
                            # this is a texture
                            color_space_item = _USDMetadataListItem(
                                self._context_name,
                                attribute_paths,
                                "colorSpace",
                                "auto",
                                ["auto", "raw", "sRGB"],
                                display_attr_names=display_attr_names,
                                display_attr_names_tooltip=descriptions,
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
