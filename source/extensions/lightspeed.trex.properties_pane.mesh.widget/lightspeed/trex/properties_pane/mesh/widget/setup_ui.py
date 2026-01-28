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

import functools
import os
import re
import typing
from typing import List, Union

import carb
import omni.client
import omni.kit.app
import omni.ui as ui
import omni.usd
from lightspeed.common import constants
from lightspeed.common.constants import PROPERTIES_NAMES_COLUMN_WIDTH
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.asset_replacements.core.shared.usd_copier import copy_usd_asset as _copy_usd_asset
from lightspeed.trex.selection_tree.widget.selection_tree.model import ItemAsset as _ItemAsset
from lightspeed.trex.selection_tree.widget.selection_tree.model import ItemInstance as _ItemInstance
from lightspeed.trex.selection_tree.widget.selection_tree.model import ItemInstancesGroup as _ItemInstancesGroup
from lightspeed.trex.selection_tree.widget.selection_tree.model import ItemPrim as _ItemPrim
from lightspeed.trex.selection_tree.widget.selection_tree.model import ItemReferenceFile as _ItemReferenceFile
from lightspeed.trex.utils.common.file_utils import (
    is_usd_file_path_valid_for_filepicker as _is_usd_file_path_valid_for_filepicker,
)
from lightspeed.trex.utils.widget import RemixCategoriesDialog as _RemixCategoriesDialog
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from omni.flux.properties_pane.properties.usd.widget import PropertyWidget as _PropertyWidget
from omni.flux.properties_pane.transformation.usd.widget import TransformPropertyWidget as _TransformPropertyWidget
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator
from omni.flux.utils.widget.file_pickers.file_picker import open_file_picker as _open_file_picker
from pxr import Sdf, UsdGeom, UsdLux

if typing.TYPE_CHECKING:
    from lightspeed.trex.selection_tree.widget.selection_tree.model import (
        ItemAddNewReferenceFile as _ItemAddNewReferenceFileMesh,
    )


class SetupUI:
    def __init__(self, context_name: str):
        """Mesh Properties Widget"""

        self._default_attr = {
            "_frame_none": None,
            "_mesh_properties_frames": None,
            "_frame_mesh_ref": None,
            "_frame_mesh_prim": None,
            "_mesh_ref_field": None,
            "_mesh_ref_field_valid": True,
            "_overlay_mesh_ref_label": None,
            "_mesh_ref_prim_field": None,
            "_mesh_ref_default_prim_checkbox": None,
            "_mesh_ref_default_prim_label": None,
            "_ignore_mesh_ref_field_changed": False,
            "_only_read_mesh_ref": False,
            "_from_mesh_ref_checkbox": False,
            "_core": None,
            "_current_reference_file_items": None,
            "_sub_mesh_ref_field_changed": None,
            "_sub_mesh_ref_prim_field_changed": None,
            "_sub_mesh_ref_default_prim_checkbox_changed": None,
            "_sub_mesh_ref_field_begin_edit": None,
            "_sub_mesh_ref_field_end_edit": None,
            "_sub_mesh_ref_prim_field_begin_edit": None,
            "_sub_mesh_ref_prim_field_end_edit": None,
            "_transformation_widget": None,
            "_property_widget": None,
            "_object_property_line": None,
            "_current_instance_items": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)
        self._core = _AssetReplacementsCore(context_name)
        self._mesh_properties_frames = {}
        self.__ignore_ingest_check = False
        self.__ref_mesh_field_is_editing = False
        self._current_reference_file_items = []
        self._current_instance_items = []
        self.__will_change_prim_field = False

        self.__create_ui()

        self.__on_go_to_ingest_tab = _Event()

    def _go_to_ingest_tab(self):
        """Call the event object that has the list of functions"""
        self.__on_go_to_ingest_tab()

    def subscribe_go_to_ingest_tab(self, func):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_go_to_ingest_tab, func)

    def __create_ui(self):
        with ui.ZStack():
            self._frame_none = ui.Frame(visible=True, identifier="frame_none")
            self._mesh_properties_frames[None] = self._frame_none
            with self._frame_none:
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(8))
                    with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                        ui.Spacer(height=0)
                        with ui.VStack(width=0):
                            ui.Spacer()
                            ui.Label("None", name="PropertiesWidgetLabel")
                            ui.Spacer()
                        ui.Spacer(height=0)
            self._frame_mesh_ref = ui.Frame(visible=False, identifier="frame_mesh_ref")
            self._mesh_properties_frames[_ItemReferenceFile] = self._frame_mesh_ref
            with self._frame_mesh_ref:
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(8))
                    with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                        with ui.HStack(width=ui.Pixel(160)):
                            ui.Spacer()
                            ui.Label(
                                "Reference USD path",
                                name="PropertiesWidgetLabel",
                                tooltip="Path of the USD reference",
                                width=0,
                            )
                        with ui.HStack():
                            ui.Spacer(width=ui.Pixel(4))
                            with ui.ZStack():
                                self._mesh_ref_field = ui.StringField(
                                    height=ui.Pixel(18),
                                    style_type_name_override="Field",
                                    identifier="mesh_ref_field",
                                )
                                with ui.HStack():
                                    ui.Spacer(width=ui.Pixel(8))
                                    with ui.Frame(width=ui.Pixel(134), horizontal_clipping=True):
                                        self._overlay_mesh_ref_label = ui.Label(
                                            "USD Reference path...",
                                            name="USDPropertiesWidgetValueOverlay",
                                            width=0,
                                        )
                                self._sub_mesh_ref_field_begin_edit = (
                                    self._mesh_ref_field.model.subscribe_begin_edit_fn(self._on_mesh_ref_field_begin)
                                )
                                self._sub_mesh_ref_field_end_edit = self._mesh_ref_field.model.subscribe_end_edit_fn(
                                    self._on_mesh_ref_field_end
                                )
                                self._sub_mesh_ref_field_changed = (
                                    self._mesh_ref_field.model.subscribe_value_changed_fn(
                                        self._on_mesh_ref_field_changed
                                    )
                                )
                            ui.Spacer(width=ui.Pixel(8))
                            with ui.VStack(width=ui.Pixel(20)):
                                ui.Spacer()
                                ui.Image(
                                    "",
                                    name="OpenFolder",
                                    height=ui.Pixel(20),
                                    mouse_pressed_fn=lambda x, y, b, m: self._on_ref_mesh_dir_pressed(b),
                                    identifier="replace_ref_open_folder",
                                )
                                ui.Spacer()

                    ui.Spacer(height=ui.Pixel(8))
                    with ui.HStack(height=ui.Pixel(48), spacing=ui.Pixel(8)):
                        with ui.HStack(width=ui.Pixel(160)):
                            ui.Spacer()
                            with ui.VStack(width=0):
                                ui.Label(
                                    "Reference prim",
                                    name="PropertiesWidgetLabel",
                                    tooltip="Prim path of the USD reference",
                                )
                                ui.Spacer()
                        with ui.HStack():
                            ui.Spacer(width=ui.Pixel(4))
                            with ui.VStack():
                                self._mesh_ref_prim_field = ui.StringField(
                                    height=ui.Pixel(18),
                                    style_type_name_override="Field",
                                    identifier="mesh_ref_prim_field",
                                )
                                self._sub_mesh_ref_prim_field_begin_edit = (
                                    self._mesh_ref_prim_field.model.subscribe_begin_edit_fn(
                                        self._on_mesh_ref_field_begin
                                    )
                                )
                                self._sub_mesh_ref_prim_field_end_edit = (
                                    self._mesh_ref_prim_field.model.subscribe_end_edit_fn(self._on_mesh_ref_field_end)
                                )
                                self._sub_mesh_ref_prim_field_changed = (
                                    self._mesh_ref_prim_field.model.subscribe_value_changed_fn(
                                        self._on_mesh_ref_field_changed
                                    )
                                )
                                ui.Spacer(height=ui.Pixel(8))
                                with ui.HStack(height=ui.Pixel(18)):
                                    self._mesh_ref_default_prim_checkbox = ui.CheckBox(
                                        width=0,
                                        identifier="mesh_ref_default_prim_checkbox",
                                    )
                                    self._sub_mesh_ref_default_prim_checkbox_changed = (
                                        self._mesh_ref_default_prim_checkbox.model.subscribe_value_changed_fn(
                                            self._on_mesh_ref_default_prim_checkbox_changed
                                        )
                                    )
                                    ui.Spacer(width=ui.Pixel(8))
                                    self._mesh_ref_default_prim_label = ui.Label("Use default prim instead", width=0)

            self._frame_mesh_prim = ui.Frame(visible=False, identifier="frame_mesh_prim")
            self._mesh_properties_frames[_ItemPrim] = self._frame_mesh_prim
            with self._frame_mesh_prim:
                with ui.VStack():
                    self._transformation_widget = _TransformPropertyWidget(
                        self._context_name,
                        tree_column_widths=[
                            PROPERTIES_NAMES_COLUMN_WIDTH,
                            ui.Fraction(1),
                        ],
                        columns_resizable=True,
                        right_aligned_labels=False,
                    )

                    self._object_property_spacer = ui.Spacer(height=ui.Pixel(8))

                    self._object_property_line = ui.Line(name="PropertiesPaneSectionTitle")

                    ui.Spacer(height=ui.Pixel(8))

                    def should_show_light_attr(prim):
                        return prim.HasAPI(UsdLux.LightAPI) if hasattr(UsdLux, "LightAPI") else prim.IsA(UsdLux.Light)

                    self._property_widget = _PropertyWidget(
                        self._context_name,
                        optional_attributes=[
                            (should_show_light_attr, attr) for attr in constants.REMIX_OPTIONAL_LIGHT_ATTRIBUTES
                        ],
                        tree_column_widths=[
                            PROPERTIES_NAMES_COLUMN_WIDTH,
                            ui.Fraction(1),
                        ],
                        columns_resizable=True,
                        right_aligned_labels=False,
                    )

                    ui.Spacer(height=ui.Pixel(8))

                    self._object_category_line = ui.Line(name="PropertiesPaneSectionTitle")

                    ui.Spacer(height=ui.Pixel(8))

                    self._remix_categories_vstack = ui.VStack(height=0, spacing=ui.Pixel(8))
                    with self._remix_categories_vstack:
                        with ui.HStack(height=0):
                            with ui.HStack(width=PROPERTIES_NAMES_COLUMN_WIDTH):
                                # Spacer to replace the mixed value, default value, and override indicators
                                ui.Spacer(width=ui.Pixel((16 + 8) * 3))
                                ui.Label(
                                    "Set Render Categories",
                                    name="PropertiesWidgetLabel",
                                )
                                ui.Spacer(width=ui.Pixel(8))
                            self._remix_categories_button = ui.Image(
                                "",
                                height=ui.Pixel(24),
                                width=ui.Pixel(24),
                                name="Categories",
                                tooltip="Please note that not all categories are available in the Toolkit Viewport.",
                                mouse_pressed_fn=lambda x, y, b, m: self._add_remix_category(b),
                            )
                        with ui.HStack(height=0):
                            ui.Spacer(height=0, width=PROPERTIES_NAMES_COLUMN_WIDTH)
                            self._remix_categories_frame = ui.ScrollingFrame(
                                visible=False,
                                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                                tooltip="To set categories, use the Render Categories window.",
                                mouse_pressed_fn=lambda x, y, b, m: self._add_remix_category(b),
                                name="CategoriesFrame",
                            )

    def refresh(
        self,
        items: List[
            Union[
                "_ItemAsset",
                "_ItemReferenceFile",
                "_ItemAddNewReferenceFileMesh",
                "_ItemInstancesGroup",
                "_ItemInstance",
                "_ItemPrim",
            ]
        ],
    ):
        found = False
        for item_type, frame in self._mesh_properties_frames.items():
            if item_type is None:
                self._mesh_properties_frames[None].visible = False
                continue
            value = any(isinstance(item, item_type) for item in items) if items else False
            frame.visible = value
            if value:
                found = True
        if not found:
            self._mesh_properties_frames[None].visible = True

        self._current_reference_file_items = [
            item for item in items if isinstance(item, _ItemReferenceFile) and item.prim.IsValid()
        ]
        self._current_instance_items = [
            item for item in items if isinstance(item, _ItemInstance) and item.prim.IsValid()
        ]
        item_prims = [
            item
            for item in items
            if isinstance(item, _ItemPrim)
            and item.prim.IsValid()
            and not item.from_live_light_group
            and not item.is_usd_light()
        ]
        item_light_prims = [
            item
            for item in items
            if isinstance(item, _ItemPrim)
            and item.prim.IsValid()
            and (item.from_live_light_group or item.is_usd_light())
        ]
        regex_light_pattern = re.compile(constants.REGEX_LIGHT_PATH)
        item_light_assets = [
            item for item in items if isinstance(item, _ItemAsset) and regex_light_pattern.match(item.path)
        ]
        if self._current_reference_file_items:
            self._transformation_widget.show(False)
            self._property_widget.show(False)
            # prefer ref properties if both present for consistency
            self._mesh_properties_frames[_ItemPrim].visible = False
            # we take only the last value
            self._only_read_mesh_ref = True
            self.set_ref_mesh_field(
                path=self._current_reference_file_items[-1].path,
                layer=self._current_reference_file_items[-1].layer,
            )
            self._only_read_mesh_ref = False
            self._remix_categories_vstack.visible = False
            self._remix_categories_frame.visible = False
        elif item_prims:
            # Get all the transformable prims from the instances
            instances = self._core.get_instance_from_mesh(
                [i.path for i in item_prims],
                [i.path for i in self._current_instance_items],
            )
            transformable_prim_paths = self._core.filter_transformable_prims(instances)
            transformable_prim_paths = list(dict.fromkeys(transformable_prim_paths))
            mesh_prims = self._core.filter_imageable_prims([item.prim for item in item_prims])
            # Refresh of the transform
            self._transformation_widget.show(bool(transformable_prim_paths))
            if transformable_prim_paths:
                self._transformation_widget.refresh(transformable_prim_paths)
                # for a regular prim, we don't show others properties
                self._property_widget.show(False)
            if mesh_prims:
                # show properties panel
                self._mesh_properties_frames[_ItemPrim].visible = True
                self._mesh_properties_frames[None].visible = False
                self._property_widget.show(True)
                # set specific attributes
                specific_attrs = [
                    UsdGeom.Tokens.doubleSided,
                ]

                self._property_widget.set_specific_attributes(specific_attrs)

                # set lookup table for meshes
                lookup_table = {
                    attr: {"name": attr.capitalize(), "group": None, "read_only": False} for attr in specific_attrs
                }
                lookup_table.update(
                    {
                        UsdGeom.Tokens.doubleSided: {
                            "name": "Double Sided",
                            "group": None,
                            "read_only": any(
                                self._core.prim_is_from_a_capture_reference(mesh_prim) for mesh_prim in mesh_prims
                            ),
                        },
                    }
                )

                self._refresh_remix_categories(mesh_prims)
                self._property_widget.set_lookup_table(lookup_table)
                self._property_widget.refresh([mesh_prim.GetPath() for mesh_prim in mesh_prims])
                self._remix_categories_vstack.visible = True
                self._remix_categories_frame.visible = True
            else:
                # we show the none panel
                self._mesh_properties_frames[_ItemPrim].visible = False
                self._mesh_properties_frames[None].visible = True
                # for a regular prim, we don't show others properties
                self._property_widget.show(False)
                self._remix_categories_vstack.visible = False
                self._remix_categories_frame.visible = False
        elif item_light_assets or item_light_prims:  # light
            # if this is a light, we can transform the light by itself. So we should show the transform frame
            prim_paths = [item.path for item in item_light_assets]

            for item in item_light_prims:
                for instance_item in self._current_instance_items:
                    to_select_path = re.sub(
                        constants.REGEX_MESH_TO_INSTANCE_SUB,
                        str(instance_item.prim.GetPath()),
                        item.path,
                    )
                    prim_paths.append(to_select_path)

            xformable_prims = self._core.filter_transformable_prims(prim_paths)
            xformable_prims = list(dict.fromkeys(xformable_prims))

            self._transformation_widget.show(bool(xformable_prims))
            self._property_widget.show(bool(xformable_prims))

            # set specific attributes
            specific_attrs = [
                UsdLux.Tokens.inputsAngle,
                UsdLux.Tokens.inputsColor,
                UsdLux.Tokens.inputsEnableColorTemperature,
                UsdLux.Tokens.inputsColorTemperature,
                UsdLux.Tokens.inputsExposure,
                UsdLux.Tokens.inputsHeight,
                UsdLux.Tokens.inputsIntensity,
                UsdLux.Tokens.inputsLength,
                UsdLux.Tokens.inputsRadius,
                UsdLux.Tokens.inputsWidth,
                UsdLux.Tokens.inputsShapingConeAngle,
                UsdLux.Tokens.inputsShapingConeSoftness,
                UsdLux.Tokens.inputsShapingFocus,
            ] + [attr["token"] for attr in constants.REMIX_OPTIONAL_LIGHT_ATTRIBUTES]
            self._property_widget.set_specific_attributes(specific_attrs)

            # set lookup table for lights
            lookup_table = {
                attr: {"name": attr.capitalize(), "group": None, "read_only": False} for attr in specific_attrs
            }
            lookup_table.update(
                {
                    UsdLux.Tokens.inputsAngle: {"name": "Angle", "group": None},
                    UsdLux.Tokens.inputsColor: {"name": "Color", "group": None},
                    UsdLux.Tokens.inputsEnableColorTemperature: {
                        "name": "Enable Color Temp.",
                        "group": None,
                    },
                    UsdLux.Tokens.inputsColorTemperature: {
                        "name": "Color Temp.",
                        "group": None,
                    },
                    UsdLux.Tokens.inputsExposure: {"name": "Exposure", "group": None},
                    UsdLux.Tokens.inputsHeight: {"name": "Height", "group": None},
                    UsdLux.Tokens.inputsIntensity: {"name": "Intensity", "group": None},
                    UsdLux.Tokens.inputsLength: {"name": "Length", "group": None},
                    UsdLux.Tokens.inputsRadius: {"name": "Radius", "group": None},
                    UsdLux.Tokens.inputsWidth: {"name": "Width", "group": None},
                    UsdLux.Tokens.inputsShapingConeAngle: {
                        "name": "Shaping: Cone Angle",
                        "group": None,
                    },
                    UsdLux.Tokens.inputsShapingConeSoftness: {
                        "name": "Shaping: Cone Softness",
                        "group": None,
                    },
                    UsdLux.Tokens.inputsShapingFocus: {
                        "name": "Shaping: Focus",
                        "group": None,
                    },
                }
            )
            lookup_table.update(
                {
                    attr["token"]: {
                        "name": attr["name"],
                        "group": None,
                        "read_only": False,
                    }
                    for attr in constants.REMIX_OPTIONAL_LIGHT_ATTRIBUTES
                }
            )
            self._property_widget.set_lookup_table(lookup_table)

            if xformable_prims:
                self._mesh_properties_frames[_ItemPrim].visible = True
                self._mesh_properties_frames[None].visible = False
            else:
                # we show the none panel
                self._mesh_properties_frames[_ItemPrim].visible = False
                self._mesh_properties_frames[None].visible = True
            self._transformation_widget.refresh(xformable_prims)
            self._property_widget.refresh(xformable_prims)
            self._remix_categories_vstack.visible = False
            self._remix_categories_frame.visible = False

        self._object_property_line.visible = all(
            [
                self._transformation_widget.visible,
                self._property_widget.visible,
                bool(self._property_widget.property_model.get_all_items()),
            ]
        )
        self._object_property_spacer.visible = self._object_property_line.visible

        self._object_category_line.visible = all(
            [
                self._property_widget.visible,
                self._remix_categories_vstack.visible,
                self._remix_categories_button.visible,
            ]
        )

    def _on_ref_mesh_dir_pressed(self, button):
        if button != 0:
            return
        navigate_to = self._mesh_ref_field.model.get_value_as_string()

        # Open the file picker to current asset location
        fallback = False
        layer = self._current_reference_file_items[0].layer
        stage = self._context.get_stage()
        if not navigate_to:
            if stage and not stage.GetRootLayer().anonymous:
                # If asset path is empty, open the USD rootlayer folder
                # But only if filepicker didn't already have a folder remembered (thus fallback)
                fallback = True
                navigate_to = os.path.dirname(stage.GetRootLayer().identifier)
            else:
                navigate_to = None
        elif layer:
            navigate_to = layer.ComputeAbsolutePath(navigate_to)

        if not self._core.is_file_path_valid(navigate_to, layer):
            fallback = True
            navigate_to = os.path.dirname(stage.GetRootLayer().identifier)

        _open_file_picker(
            "Select a reference file",
            callback=functools.partial(self.set_ref_mesh_field, layer=layer),
            callback_cancel=lambda *args: None,
            current_file=navigate_to,
            fallback=fallback,
            file_extension_options=constants.READ_USD_FILE_EXTENSIONS_OPTIONS,
            validate_selection=_is_usd_file_path_valid_for_filepicker,
            validation_failed_callback=self.__show_error_not_usd_file,
        )

    def __show_error_not_usd_file(self, dirname: str, filename: str):
        _TrexMessageDialog(
            message=f"{dirname}/{filename} is not a USD file",
            disable_cancel_button=True,
        )

    def _on_mesh_ref_field_begin(self, _model):
        self.__ref_mesh_field_is_editing = True

    def _on_mesh_ref_field_end(self, model):
        self.__ref_mesh_field_is_editing = False
        self._on_mesh_ref_field_changed(model)

    def _on_mesh_ref_field_changed(self, _model):
        self._do_mesh_ref_field_changed()

    def set_ref_mesh_field(self, path, change_prim_field=True, layer: "Sdf.Layer" = None):
        self.__will_change_prim_field = change_prim_field
        if self._only_read_mesh_ref:
            value = path
        else:
            value = path.replace("\\", "/")
            if not self.__ignore_ingest_check and not self.__was_asset_ingested(value):
                return

            if layer is not None and not self._core.asset_is_in_project_dir(value, layer):
                self.__prompt_user_to_copy_usd_asset(path=value, layer=layer)
                return

        self._mesh_ref_field.model.set_value(value)
        if change_prim_field:
            self._ignore_mesh_ref_field_changed = True
            self.__set_ref_mesh_prim_field()
            self._ignore_mesh_ref_field_changed = False

    def __prompt_user_to_copy_usd_asset(self, path: str, layer: "Sdf.Layer"):
        self.__ignore_ingest_check = True

        # Prompt the user copy the asset or cancel
        _TrexMessageDialog(
            title=constants.ASSET_OUTSIDE_OF_PROJ_DIR_TITLE,
            message=constants.ASSET_OUTSIDE_OF_PROJ_DIR_MESSAGE,
            disable_ok_button=False,
            ok_label=constants.ASSET_OUTSIDE_OF_PROJ_DIR_OK_LABEL,
            ok_handler=functools.partial(
                _copy_usd_asset,
                context=self._context,
                asset_path=path,
                callback_func=lambda x: self.set_ref_mesh_field(path=x, change_prim_field=True, layer=layer),
            ),
            disable_middle_button=True,
            disable_cancel_button=False,
        )

    def __set_ref_mesh_prim_field(self):
        if not self._current_reference_file_items:
            return

        asset_path = self._mesh_ref_field.model.get_value_as_string()
        layer = self._current_reference_file_items[-1].layer
        if self._only_read_mesh_ref:
            ref_prim_path = (
                str(self._current_reference_file_items[-1].ref.primPath) or self._core.get_ref_default_prim_tag()
            )
        else:
            edit_target_layer = self._context.get_stage().GetEditTarget().GetLayer()
            ref_prim_path = self._core.get_reference_prim_path_from_asset_path(
                asset_path,
                layer,
                edit_target_layer,
                self._current_reference_file_items[-1].ref,
            )
        prim_path_is_default = self._core.ref_prim_path_is_default_prim(ref_prim_path)
        self._mesh_ref_prim_field.model.set_value(ref_prim_path)
        self._mesh_ref_prim_field.read_only = prim_path_is_default

        # update the checkbox
        self._mesh_ref_default_prim_checkbox.model.set_value(prim_path_is_default)

    def _on_mesh_ref_default_prim_checkbox_changed(self, model):
        value = model.get_value_as_bool()
        self._mesh_ref_prim_field.read_only = value
        self._from_mesh_ref_checkbox = True
        if value:
            self._mesh_ref_prim_field.model.set_value(self._core.get_ref_default_prim_tag())
        else:
            asset_path = self._mesh_ref_field.model.get_value_as_string()
            layer = self._current_reference_file_items[-1].layer
            ref_prim_path = self._core.get_reference_prim_path_from_asset_path(
                asset_path,
                layer,
                layer,
                self._current_reference_file_items[-1].ref,
                can_return_default=False,
            )
            self._mesh_ref_prim_field.model.set_value(ref_prim_path)
        self._from_mesh_ref_checkbox = False

    def __reset_ingest_asset(self, go_to_ingest: bool = False):
        self._ignore_mesh_ref_field_changed = True
        self._only_read_mesh_ref = True
        self.set_ref_mesh_field(
            path=self._current_reference_file_items[-1].path,
            change_prim_field=False,
        )
        self._ignore_mesh_ref_field_changed = False
        self._only_read_mesh_ref = False
        if go_to_ingest:
            self._go_to_ingest_tab()

    def __ignore_warning_ingest_asset(self, path):
        self.__ignore_ingest_check = True
        self._ignore_mesh_ref_field_changed = False
        # we trigger the ref field by hand. Because if the value in the field is the same, this is not triggered
        self._sub_mesh_ref_field_changed = None
        self.set_ref_mesh_field(path)
        self._do_mesh_ref_field_changed()
        # add it back
        self._sub_mesh_ref_field_changed = self._mesh_ref_field.model.subscribe_value_changed_fn(
            self._on_mesh_ref_field_changed
        )
        self.__ignore_ingest_check = False

    def __was_asset_ingested(self, path) -> bool:
        if not self._only_read_mesh_ref and not self.__ref_mesh_field_is_editing and not self._from_mesh_ref_checkbox:
            layer = self._context.get_stage().GetEditTarget().GetLayer()
            abs_new_asset_path = omni.client.normalize_url(layer.ComputeAbsolutePath(path))

            # Check if asset ingested
            if not self._core.was_the_asset_ingested(abs_new_asset_path):
                ingest_enabled = bool(
                    omni.kit.app.get_app()
                    .get_extension_manager()
                    .get_enabled_extension_id("lightspeed.trex.control.ingestcraft")
                )

                _TrexMessageDialog(
                    title=constants.ASSET_NEED_INGEST_WINDOW_TITLE,
                    message=constants.ASSET_NEED_INGEST_MESSAGE,
                    ok_handler=functools.partial(self.__ignore_warning_ingest_asset, path=path),
                    ok_label=constants.ASSET_NEED_INGEST_WINDOW_OK_LABEL,
                    cancel_handler=self.__reset_ingest_asset,
                    on_window_closed_fn=self.__reset_ingest_asset,
                    disable_ok_button=not self._core.asset_is_in_project_dir(path=abs_new_asset_path, layer=layer),
                    disable_cancel_button=False,
                    disable_middle_button=not ingest_enabled,
                    middle_label=constants.ASSET_NEED_INGEST_WINDOW_MIDDLE_LABEL,
                    middle_handler=functools.partial(self.__reset_ingest_asset, go_to_ingest=True),
                )
                return False
        return True

    @_ignore_function_decorator(attrs=["_ignore_mesh_ref_field_changed"])
    def _do_mesh_ref_field_changed(self):
        # check asset path
        path = self._mesh_ref_field.model.get_value_as_string()
        will_change_prim_field = bool(self.__will_change_prim_field)
        self._overlay_mesh_ref_label.visible = not bool(path.strip())
        is_abs = self._core.is_absolute_path(path)
        layer = self._current_reference_file_items[0].layer
        abs_path = omni.client.normalize_url(layer.ComputeAbsolutePath(path))
        set_new_ref = True
        # If read mode, we don't change the path.
        # If this is from the checkbox, because the checkbox will apply on the edit layer,
        # we regenerate the relative path from the edit layer
        if not self._only_read_mesh_ref:
            if is_abs:  # if it is absolute, generate relative path.
                path = self._core.switch_ref_abs_to_rel_path(self._context.get_stage(), path)
            else:  # If the path is relative, we regenerate it relative to the edit layer
                if self._from_mesh_ref_checkbox and self._mesh_ref_field_valid:
                    layer = self._current_reference_file_items[0].layer
                else:
                    layer = self._context.get_stage().GetEditTarget().GetLayer()
                abs_path = omni.client.normalize_url(layer.ComputeAbsolutePath(path))
                path = self._core.switch_ref_abs_to_rel_path(self._context.get_stage(), abs_path)
        if not self.__is_ref_field_path_valid(path):
            set_new_ref = False

        # disable mesh ref field
        ref_from_capture = self._core.ref_path_is_from_capture(abs_path)
        self._mesh_ref_prim_field.enabled = not ref_from_capture
        self._mesh_ref_default_prim_checkbox.enabled = not ref_from_capture

        # check if the asset was ingested
        if set_new_ref and not self.__ignore_ingest_check and not self.__was_asset_ingested(path):
            return

        if self.__ref_mesh_field_is_editing:
            return

        # check prim path
        if not will_change_prim_field:
            prim_path = self._mesh_ref_prim_field.model.get_value_as_string()
            if set_new_ref and not self.__is_ref_prim_field_path_valid(path, prim_path):
                set_new_ref = False

        # if the path is a valid asset and outside of project hierarchy, prompt the user to copy or cancel
        if self._core.is_file_path_valid(
            path=abs_path, layer=layer, log_error=False
        ) and not self._core.asset_is_in_project_dir(path=abs_path, layer=layer, include_deps_dir=True):
            self.__prompt_user_to_copy_usd_asset(path=abs_path, layer=layer)

        if set_new_ref and not self._only_read_mesh_ref and self._core.asset_is_in_project_dir(abs_path, layer):
            self.set_new_usd_reference()
        elif not self._from_mesh_ref_checkbox:
            only_read_mesh_ref_was_true = self._only_read_mesh_ref
            if not only_read_mesh_ref_was_true:
                self._only_read_mesh_ref = True
            self._ignore_mesh_ref_field_changed = False
            self.set_ref_mesh_field(
                path=self._current_reference_file_items[-1].path,
                layer=self._current_reference_file_items[-1].layer,
            )
            if not only_read_mesh_ref_was_true:
                self._only_read_mesh_ref = False
            self._ignore_mesh_ref_field_changed = True

    def __is_ref_field_path_valid(self, path) -> bool:
        if self._only_read_mesh_ref or self._from_mesh_ref_checkbox:
            layer = self._current_reference_file_items[0].layer
        else:
            layer = self._context.get_stage().GetEditTarget().GetLayer()
        if not self._core.is_file_path_valid(path, layer, log_error=False):
            self._mesh_ref_field.style_type_name_override = "FieldError"
            self._mesh_ref_field_valid = False
            return False
        self._mesh_ref_field.style_type_name_override = "Field"
        self._mesh_ref_field_valid = True
        return True

    def __is_ref_prim_field_path_valid(self, path, prim_path) -> bool:
        if self._only_read_mesh_ref or self._from_mesh_ref_checkbox:
            layer = self._current_reference_file_items[0].layer
        else:
            layer = self._context.get_stage().GetEditTarget().GetLayer()
        if not self._core.is_ref_prim_path_valid(path, prim_path, layer, log_error=False):
            self._mesh_ref_prim_field.style_type_name_override = "FieldError"
            return False
        self._mesh_ref_prim_field.style_type_name_override = "Field"
        return True

    def set_new_usd_reference(self):
        with omni.kit.undo.group():
            stage = self._context.get_stage()
            prim_path = self._current_reference_file_items[-1].prim.GetPath()
            current_ref = self._current_reference_file_items[-1].ref
            current_layer = self._current_reference_file_items[-1].layer

            # first we delete the ref
            self._core.remove_reference(stage, prim_path, current_ref, current_layer, remove_if_remix_ref=False)

            # second we add the new one
            edit_target_layer = stage.GetEditTarget().GetLayer()
            asset_path = self._mesh_ref_field.model.get_value_as_string()
            ref_prim_path = self._core.get_reference_prim_path_from_asset_path(
                asset_path, current_layer, edit_target_layer, current_ref
            )

            new_ref, prim_path = self._core.add_new_reference(
                stage,
                prim_path,
                asset_path,
                ref_prim_path,
                edit_target_layer,
                create_if_remix_ref=False,
            )
            if new_ref:
                carb.log_info(
                    f"Set new ref {new_ref.assetPath} {new_ref.primPath}, "
                    f"layer {self._context.get_stage().GetEditTarget().GetLayer()}"
                )
                # select the new prim of the new added ref
                self._core.select_child_from_instance_item_and_ref(
                    stage,
                    stage.GetPrimAtPath(prim_path),
                    new_ref.assetPath,
                    self._current_instance_items,
                    only_imageable=True,
                    filter_scope_prim_without_imageable=True,
                )
            else:
                carb.log_info("No reference set")

    def _refresh_remix_categories(self, mesh_prims):
        # Check render categories to see if any are applied
        remix_attrs = {}
        decals = []
        decal_static_name = constants.REMIX_CATEGORIES["Decal"]["attr"]
        decal_display_name = "Decal"
        for attr in mesh_prims[0].GetAttributes():
            attr_name = attr.GetName()
            display_name = constants.REMIX_CATEGORIES_DISPLAY_NAMES.get(attr_name, "")
            if display_name:
                remix_attrs[display_name] = attr.Get()

            # Checking for deprecated decal types
            if "decal" in attr_name and decal_static_name not in attr_name:
                decals.append(attr.Get())

        # Convert deprecated decal types to decal_Static
        if decal_display_name not in remix_attrs and decals:
            value = any(decals)
            self._core.add_attribute(
                [mesh_prims[0].GetPath()],
                decal_static_name,
                value,
                False,
                Sdf.ValueTypeNames.Bool,
            )
            remix_attrs[decal_display_name] = value

        any_true = [v for v in remix_attrs.values() if v]
        # If there are no values, or they are all False, hide the scrolling frame
        if not any_true or not remix_attrs:
            with self._remix_categories_frame:
                ui.VStack()
            self._remix_categories_frame.height = ui.Pixel(0)
            return

        with self._remix_categories_frame:
            with ui.VStack():
                for key, value in remix_attrs.items():
                    if not value:
                        continue
                    with ui.HStack(height=ui.Pixel(20)):
                        ui.CheckBox(enabled=False, width=24).model.set_value(value)
                        ui.Spacer(width=8)
                        ui.Label(key, name="RemixAttrLabel", alignment=ui.Alignment.LEFT)
                        ui.Spacer()
            self._remix_categories_frame.height = ui.Pixel(100)

    def _add_remix_category(self, b):
        """Provide dialog to set render categories."""
        dialog = _RemixCategoriesDialog(context_name=self._context_name, refresh_func=self._refresh_remix_categories)
        dialog.show()

    def show(self, value):
        self._transformation_widget.show(value)
        self._property_widget.show(value)

    def destroy(self):
        _reset_default_attrs(self)
