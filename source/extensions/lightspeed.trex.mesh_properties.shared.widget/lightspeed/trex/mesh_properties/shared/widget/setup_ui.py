"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import os
import typing
from typing import List, Union

import carb
import omni.client
import omni.ui as ui
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import (
    ItemReferenceFileMesh as _ItemReferenceFileMesh,
)
from lightspeed.trex.utils.common import ignore_function_decorator as _ignore_function_decorator
from lightspeed.trex.utils.widget.file_pickers.mesh_ref_file_picker import open_file_picker as _open_file_picker
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.label import create_label_with_font as _create_label_with_font

if typing.TYPE_CHECKING:
    from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import (
        ItemAddNewReferenceFileMesh as _ItemAddNewReferenceFileMesh,
    )
    from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import ItemInstanceMesh as _ItemInstanceMesh
    from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import (
        ItemInstancesMeshGroup as _ItemInstancesMeshGroup,
    )
    from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import ItemMesh as _ItemMesh


class SetupUI:
    def __init__(self, context):
        """Nvidia StageCraft Viewport UI"""

        self._default_attr = {
            "_frame_none": None,
            "_mesh_properties_frames": None,
            "_mesh_none_provider_label": None,
            "_frame_mesh_ref": None,
            "_mesh_ref_provider_label": None,
            "_mesh_ref_field": None,
            "_overlay_mesh_ref_label": None,
            "_mesh_ref_default_prim_provider_label": None,
            "_mesh_ref_prim_field": None,
            "_mesh_ref_default_prim_checkbox": None,
            "_mesh_ref_default_prim_label": None,
            "_ignore_mesh_ref_field_changed": False,
            "_only_read_mesh_ref": False,
            "_from_mesh_ref_checkbox": False,
            "_core": None,
            "_current_reference_file_mesh_items": None,
            "_sub_mesh_ref_field_changed": None,
            "_sub_mesh_ref_prim_field_changed": None,
            "_sub_mesh_ref_default_prim_checkbox_changed": None,
            "_sub_mesh_ref_field_begin_edit": None,
            "_sub_mesh_ref_field_end_edit": None,
            "_sub_mesh_ref_prim_field_begin_edit": None,
            "_sub_mesh_ref_prim_field_end_edit": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context = context
        self._core = _AssetReplacementsCore(self._context)
        self._mesh_properties_frames = {}
        self.__ref_mesh_field_is_editing = False
        self._current_reference_file_mesh_items = []
        self.__create_ui()

    def __create_ui(self):
        with ui.ZStack():
            self._frame_none = ui.Frame(visible=True)
            self._mesh_properties_frames[None] = self._frame_none
            with self._frame_none:
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(8))
                    with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                        ui.Spacer(height=0)
                        with ui.VStack(width=0):
                            ui.Spacer()
                            self._mesh_none_provider_label, _, _ = _create_label_with_font(
                                "None", "PropertiesWidgetLabel", remove_offset=False
                            )
                            ui.Spacer()
                        ui.Spacer(height=0)
            self._frame_mesh_ref = ui.Frame(visible=False)
            self._mesh_properties_frames[_ItemReferenceFileMesh] = self._frame_mesh_ref
            with self._frame_mesh_ref:
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(8))
                    with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                        with ui.HStack(width=ui.Percent(40)):
                            ui.Spacer()
                            with ui.VStack(width=0):
                                ui.Spacer()
                                self._mesh_ref_provider_label, _, _ = _create_label_with_font(
                                    "Reference USD path",
                                    "PropertiesWidgetLabel",
                                    remove_offset=False,
                                    tooltip="Path of the USD reference",
                                )
                                ui.Spacer()
                        with ui.HStack():
                            ui.Spacer(width=ui.Pixel(4))
                            with ui.ZStack():
                                self._mesh_ref_field = ui.StringField(
                                    height=ui.Pixel(18), style_type_name_override="Field"
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
                                )
                                ui.Spacer()

                    ui.Spacer(height=ui.Pixel(8))
                    with ui.HStack(height=ui.Pixel(48), spacing=ui.Pixel(8)):
                        with ui.HStack(width=ui.Percent(40)):
                            ui.Spacer()
                            with ui.VStack(width=0):
                                ui.Spacer(height=ui.Pixel(4))
                                self._mesh_ref_default_prim_provider_label, _, _ = _create_label_with_font(
                                    "Reference prim",
                                    "PropertiesWidgetLabel",
                                    remove_offset=False,
                                    tooltip="Prim path of the USD reference",
                                )
                                ui.Spacer()
                        with ui.HStack():
                            ui.Spacer(width=ui.Pixel(4))
                            with ui.VStack():
                                self._mesh_ref_prim_field = ui.StringField(
                                    height=ui.Pixel(18), style_type_name_override="Field"
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
                                    self._mesh_ref_default_prim_checkbox = ui.CheckBox(width=0)
                                    self._sub_mesh_ref_default_prim_checkbox_changed = (
                                        self._mesh_ref_default_prim_checkbox.model.subscribe_value_changed_fn(
                                            self._on_mesh_ref_default_prim_checkbox_changed
                                        )
                                    )
                                    ui.Spacer(width=ui.Pixel(8))
                                    self._mesh_ref_default_prim_label = ui.Label("Use default prim instead", width=0)

    def refresh(
        self,
        items: List[
            Union[
                "_ItemMesh",
                _ItemReferenceFileMesh,
                "_ItemAddNewReferenceFileMesh",
                "_ItemInstancesMeshGroup",
                "_ItemInstanceMesh",
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

        self._current_reference_file_mesh_items = [item for item in items if isinstance(item, _ItemReferenceFileMesh)]
        if self._current_reference_file_mesh_items:
            # we take only the last value
            self._only_read_mesh_ref = True
            self.set_ref_mesh_field(self._current_reference_file_mesh_items[-1].path)
            self._only_read_mesh_ref = False

    def _on_ref_mesh_dir_pressed(self, button):
        if button != 0:
            return
        navigate_to = self._mesh_ref_field.model.get_value_as_string()

        # Open the file picker to current asset location
        fallback = False
        layer = self._current_reference_file_mesh_items[0].layer
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

        _open_file_picker(self.set_ref_mesh_field, lambda *args: None, current_file=navigate_to, fallback=fallback)

    def _on_mesh_ref_field_begin(self, _model):
        self.__ref_mesh_field_is_editing = True

    def _on_mesh_ref_field_end(self, model):
        self.__ref_mesh_field_is_editing = False
        self._on_mesh_ref_field_changed(model)

    def _on_mesh_ref_field_changed(self, _model):
        self._do_mesh_ref_field_changed()

    def set_ref_mesh_field(self, path, change_prim_field=True):
        if self._only_read_mesh_ref:
            value = path
        else:
            value = path.replace("\\", "/")
        self._mesh_ref_field.model.set_value(value)
        if change_prim_field:
            self.__set_ref_mesh_prim_field()

    def __set_ref_mesh_prim_field(self):
        asset_path = self._mesh_ref_field.model.get_value_as_string()
        layer = self._current_reference_file_mesh_items[-1].layer
        if self._only_read_mesh_ref:
            ref_prim_path = (
                str(self._current_reference_file_mesh_items[-1].ref.primPath) or self._core.get_ref_default_prim_tag()
            )
        else:
            edit_target_layer = self._context.get_stage().GetEditTarget().GetLayer()
            ref_prim_path = self._core.get_reference_prim_path_from_asset_path(
                asset_path, layer, edit_target_layer, self._current_reference_file_mesh_items[-1].ref
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
            layer = self._current_reference_file_mesh_items[-1].layer
            ref_prim_path = self._core.get_reference_prim_path_from_asset_path(
                asset_path, layer, layer, self._current_reference_file_mesh_items[-1].ref, can_return_default=False
            )
            self._mesh_ref_prim_field.model.set_value(ref_prim_path)
        self._from_mesh_ref_checkbox = False

    @_ignore_function_decorator(attrs=["_ignore_mesh_ref_field_changed"])
    def _do_mesh_ref_field_changed(self):
        # check asset path
        path = self._mesh_ref_field.model.get_value_as_string()
        self._overlay_mesh_ref_label.visible = not bool(path.strip())
        is_abs = self._core.is_absolute_path(path)
        set_new_ref = True
        # If read mode, we don't change the path.
        # If this is from the checkbox, because the checkbox will apply on the edit layer,
        # we regenerate the relative path from the edit layer
        if not self._only_read_mesh_ref:
            if is_abs:  # if it is absolute, generate relative path.
                path = self._core.switch_ref_abs_to_rel_path(self._context.get_stage(), path)
            else:  # If the path is relative, we regenerate it relative to the edit layer
                layer = self._current_reference_file_mesh_items[0].layer
                abs_path = omni.client.normalize_url(layer.ComputeAbsolutePath(path))
                path = self._core.switch_ref_abs_to_rel_path(self._context.get_stage(), abs_path)
        if not self.__is_ref_field_path_valid(path):
            set_new_ref = False
        self.set_ref_mesh_field(path, change_prim_field=False)

        # check prim path
        prim_path = self._mesh_ref_prim_field.model.get_value_as_string()
        if not self.__is_ref_prim_field_path_valid(path, prim_path):
            set_new_ref = False

        if self.__ref_mesh_field_is_editing:
            return

        if set_new_ref and not self._only_read_mesh_ref:
            self.set_new_usd_reference()

    def __is_ref_field_path_valid(self, path) -> bool:
        if self._only_read_mesh_ref or self._from_mesh_ref_checkbox:
            layer = self._current_reference_file_mesh_items[0].layer
        else:
            layer = self._context.get_stage().GetEditTarget().GetLayer()
        if not self._core.is_file_path_valid(path, layer, log_error=False):
            self._mesh_ref_field.style_type_name_override = "FieldError"
            return False
        self._mesh_ref_field.style_type_name_override = "Field"
        return True

    def __is_ref_prim_field_path_valid(self, path, prim_path) -> bool:
        layer = self._current_reference_file_mesh_items[0].layer
        if not self._core.is_ref_prim_path_valid(path, prim_path, layer, log_error=False):
            self._mesh_ref_prim_field.style_type_name_override = "FieldError"
            return False
        self._mesh_ref_prim_field.style_type_name_override = "Field"
        return True

    def set_new_usd_reference(self):
        asset_path = self._mesh_ref_field.model.get_value_as_string()
        prim_path = self._mesh_ref_prim_field.model.get_value_as_string()
        stage = self._context.get_stage()
        new_ref = self._core.on_reference_edited(
            stage,
            self._current_reference_file_mesh_items[-1].prim.GetPath(),
            self._current_reference_file_mesh_items[-1].ref,
            asset_path,
            prim_path,
            self._current_reference_file_mesh_items[-1].layer,
        )
        if new_ref:
            carb.log_info(
                (
                    f"Set new ref {new_ref.assetPath} {new_ref.primPath},"
                    f" layer {self._context.get_stage().GetEditTarget().GetLayer()}"
                )
            )
        else:
            carb.log_info("No ref set")

    def destroy(self):
        _reset_default_attrs(self)
