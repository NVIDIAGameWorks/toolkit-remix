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

import asyncio
import functools
import re
from functools import partial
from pathlib import Path

import carb
import omni.client
import omni.kit.app
from lightspeed.common import constants as _constants
from lightspeed.common.constants import PROPERTIES_NAMES_COLUMN_WIDTH
from lightspeed.tool.material.core import ToolMaterialCore as _ToolMaterialCore
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.asset_replacements.core.shared.usd_copier import copy_non_usd_asset as _copy_non_usd_asset
from lightspeed.trex.contexts import get_instance as _trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as _Contexts
from lightspeed.trex.material.core.shared import Setup as _MaterialCore
from lightspeed.trex.utils.common.prim_utils import get_reference_file_paths as _get_reference_file_paths
from lightspeed.trex.utils.common.prim_utils import is_instance as _is_instance
from lightspeed.trex.utils.common.prim_utils import is_material_prototype as _is_material_prototype
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from omni import ui, usd
from omni.flux.asset_importer.core import determine_ideal_types as _determine_ideal_types
from omni.flux.asset_importer.core import get_texture_type_from_filename as _get_texture_type_from_filename
from omni.flux.asset_importer.core import parse_texture_paths as _parse_texture_paths
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS as _SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP as _TEXTURE_TYPE_INPUT_MAP
from omni.flux.properties_pane.materials.usd.widget import MaterialPropertyWidget as _MaterialPropertyWidget
from omni.flux.property_widget_builder.model.usd import FileTexturePicker as _FileTexturePicker
from omni.flux.property_widget_builder.model.usd import USDBuilderList as _USDBuilderList
from omni.flux.property_widget_builder.model.usd import mapping as _mapping
from omni.flux.property_widget_builder.model.usd import utils as usd_properties_utils
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.path_utils import get_invalid_extensions as _get_invalid_extensions
from omni.flux.utils.widget.file_pickers import open_file_picker as _open_file_picker
from omni.kit.window.drop_support import ExternalDragDrop as _ExternalDragDrop
from pxr import Sdf, Usd, UsdShade

from .texture_assignment_model import Delegate, Model


class TextureDialog(ui.Window):
    def hide(self):
        self.visible = False


class SetupUI:

    MATERIAL_LABEL_NAME_SIZE = 32
    _WIDGET_PADDING = 16
    MAT_PROP_FRAME = "material_property_frame"

    def __init__(self, context_name: str):
        """Nvidia StageCraft Viewport UI"""

        self._default_attr = {
            "_context_name": None,
            "_core": None,
            "_stage": None,
            "_frame_none": None,
            "_material_properties_frames": None,
            "_context_menu": None,
            "_current_material": None,
            "_current_material_label": None,
            "_current_material_mdl_file_label": None,
            "_frame_material_widget": None,
            "_material_properties_widget": None,
            "_frame_combobox_materials": None,
            "_convert_opaque_button": None,
            "_convert_translucent_button": None,
            "_sub_on_material_refresh_done": None,
            "_external_drag_and_drop": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._context = usd.get_context(self._context_name)
        self._asset_replacement_core = _AssetReplacementsCore(context_name)
        self._core = _MaterialCore(context_name)
        self.set_external_drag_and_drop()  # disable REMIX-3008

        self._stage = usd.get_context(self._context_name).get_stage()

        self._current_single_material: Sdf.Path | None = None
        self._current_material_mdl_file: Path | None = None
        self._selected_prims: list[Usd.Prim] = []
        self._material_properties_frames = {}

        # Populated during a right click event within `_show_copy_menu` to avoid garbage collection
        self._context_menu: ui.Menu | None = None

        self.__create_ui()

        self.__on_material_changed = _Event()
        self.__on_go_to_ingest_tab = _Event()

    def set_external_drag_and_drop(self, window_name=_constants.WINDOW_NAME):
        self._external_drag_and_drop = _ExternalDragDrop(window_name=window_name, drag_drop_fn=self._drop_texture)

    def _go_to_ingest_tab(self):
        """Call the event object that has the list of functions"""
        self.__on_go_to_ingest_tab()

    def subscribe_go_to_ingest_tab(self, func):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_go_to_ingest_tab, func)

    def __show_material_menu(self):
        self.__menu.show()

    def get_custom_field_builders(self) -> _USDBuilderList:
        field_builders = _USDBuilderList()

        # Customize the sdf asset path attribute widgets to limit file extension to dds.
        @field_builders.register_by_type(_mapping.tf_sdf_asset_path)
        def _sdf_asset_path_builder(item) -> list[ui.Widget]:
            builder = _FileTexturePicker(
                file_extension_options=[("*.dds", "Compatible Textures")],
                regex_hash=_constants.COMPILED_REGEX_HASH_GENERIC,
            )
            return builder(item)

        return field_builders

    def __create_ui(self):
        with ui.ZStack():
            self._frame_none = ui.Frame(visible=True, identifier="frame_none")
            self._material_properties_frames[None] = self._frame_none
            with self._frame_none:
                with ui.VStack(height=ui.Pixel(32)):
                    ui.Label("None", name="PropertiesWidgetLabel", alignment=ui.Alignment.CENTER)
            self._frame_material_widget = ui.Frame(visible=False, identifier="frame_material_widget")
            self._material_properties_frames[self.MAT_PROP_FRAME] = self._frame_material_widget

            with self._frame_material_widget:
                with ui.VStack(spacing=ui.Pixel(8)):
                    ui.Spacer(height=0)
                    with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                        ui.Label(
                            "Material:",
                            name="PropertiesWidgetLabel",
                            alignment=ui.Alignment.RIGHT_CENTER,
                            width=ui.Pixel(30),
                        )
                        with ui.ZStack():
                            ui.Rectangle(width=ui.Percent(100))
                            with ui.HStack(height=ui.Pixel(24)):
                                ui.Spacer(width=ui.Pixel(8), height=0)
                                self._current_material_label = ui.Label(
                                    "",
                                    name="PropertiesWidgetLabel",
                                    identifier="material_label",
                                    alignment=ui.Alignment.LEFT_CENTER,
                                    tooltip="",
                                    elided_text=True,
                                    mouse_pressed_fn=lambda x, y, b, m: self._show_copy_menu(b),
                                )
                        ui.Image(
                            "",
                            name="MenuBurger",
                            height=ui.Pixel(24),
                            width=ui.Pixel(24),
                            mouse_pressed_fn=lambda x, y, b, m: self.__show_material_menu(),
                        )
                    with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                        ui.Label(
                            "MDL file:",
                            name="PropertiesWidgetLabel",
                            alignment=ui.Alignment.RIGHT_CENTER,
                            width=ui.Pixel(30),
                        )
                        with ui.ZStack():
                            ui.Rectangle(width=ui.Percent(100))
                            with ui.HStack(height=ui.Pixel(24)):
                                ui.Spacer(width=ui.Pixel(8), height=0)
                                self._current_material_mdl_file_label = ui.Label(
                                    "",
                                    name="PropertiesWidgetLabel",
                                    alignment=ui.Alignment.LEFT_CENTER,
                                    tooltip="",
                                    elided_text=True,
                                    mouse_pressed_fn=lambda x, y, b, m: self._show_copy_menu(b),
                                )

                    ui.Button(
                        text="Assign Texture Sets",
                        identifier="AssignTextureSetButton",
                        clicked_fn=self.__check_for_similar_textures,
                        height=ui.Pixel(8),
                    )

                    self._material_properties_widget = _MaterialPropertyWidget(
                        self._context_name,
                        tree_column_widths=[PROPERTIES_NAMES_COLUMN_WIDTH, ui.Fraction(1)],
                        columns_resizable=True,
                        right_aligned_labels=False,
                        create_color_space_attributes=False,
                        field_builders=self.get_custom_field_builders(),
                    )

        self._sub_on_material_refresh_done = self._material_properties_widget.subscribe_refresh_done(
            self._on_material_refresh_done
        )

    def _drop_texture(self, event: _ExternalDragDrop, payload: list[str]):
        """Function to do the work when dragging and dropping textures"""

        # Make sure we aren't in either of the ingest contexts
        context_inst = _trex_contexts_instance()
        try:
            context = context_inst.get_current_context()
        except RuntimeError:
            context = None
        if context is not _Contexts.STAGE_CRAFT:
            return

        # Only do work if there are material settings and prims available to work on
        items = self._material_properties_widget.property_model.get_all_items()
        prim_paths = self._context.get_selection().get_selected_prim_paths()
        if not prim_paths or not items:
            return

        # Make sure that it's an appropriate texture extension and use a dds if one is available
        dropped_paths: list[Path] = []
        basename = None
        for source in event.expand_payload(payload):
            path = Path(source)
            if _get_invalid_extensions(file_paths=[path], valid_extensions=_SUPPORTED_TEXTURE_EXTENSIONS):
                continue

            found_dds = list(path.parent.glob(f"{path.stem}*.[dD][dD][sS]"))
            if found_dds:
                path = found_dds[0]
            dropped_paths.append(path)
            if not basename:
                basename = path.name

        other_dds_paths = dropped_paths[0].parent.glob("*.[dD][dD][sS]")
        dropped_paths.extend(other_dds_paths)
        self._texture_assignment(dropped_paths, items, allow_dialog_skip=False, basename=basename)

    def _on_material_refresh_done(self):
        """
        Set callback that will check if an asset was ingested. For now, we handle only Asset type (texture) from
        material. And setting callback for setting texture edit status.
        """
        items = self._material_properties_widget.property_model.get_all_items()
        for item in items:
            for value_model in item.value_models:
                if usd_properties_utils.get_type_name(value_model.metadata) in [Sdf.ValueTypeNames.Asset]:
                    value_model.set_callback_pre_set_value(self.__check_asset_was_ingested_and_in_proj_dir)

    def _texture_assignment(
        self, selected_paths: list[Path], items, allow_dialog_skip=True, basename=None, found_paths=None
    ):
        """
        Sort textures before updating the texture fields. Show a dialog to give options before
        updating to confirm the user's intention.
        """
        texture_dict = {}

        basename_parts = _parse_texture_paths([basename])
        # If it's an already ingested texture, we can just ignore the tags
        if basename_parts[basename][-1] == "rtex":
            basename_parts = basename_parts[basename][:-2]
        else:
            basename_parts = basename_parts[basename]
        base_parts_len = len(basename_parts)
        all_path_parts = _parse_texture_paths([p.name for p in selected_paths])

        for path in selected_paths:
            if path.suffix != ".dds":
                continue
            texture_type = _get_texture_type_from_filename(str(path))
            # If it's an already ingested texture, we can just ignore the tags
            path_parts = all_path_parts[path.name]
            if path_parts[-1] == "rtex":
                path_parts = path_parts[:-2]
            similar_len = len([c for c in basename_parts if c in path_parts])
            if similar_len == 0:
                continue
            if texture_type and similar_len >= base_parts_len - 1:
                name = _TEXTURE_TYPE_INPUT_MAP[texture_type].replace("inputs:", "")
                if name not in texture_dict:
                    texture_dict[name] = str(path)

        for _, value in texture_dict.items():
            selected_paths.remove(Path(value))

        texture_types = _determine_ideal_types([str(path) for path in selected_paths])
        for path, texture_type in texture_types.items():
            if _TEXTURE_TYPE_INPUT_MAP[texture_type].replace("inputs:", "") in texture_dict:
                continue
            path_name = Path(path).name
            similar_len = len([c for c in basename_parts if c in path_name])
            if similar_len == 0:
                continue
            if similar_len >= base_parts_len - 1:
                texture_dict[_TEXTURE_TYPE_INPUT_MAP[texture_type].replace("inputs:", "")] = path

        if not texture_dict:
            carb.log_warn("Could not determine texture type(s) or no textures found. Skipping...")
            _TrexMessageDialog(
                title="Texture Set Error",
                message="Could not determine texture type(s) or no textures found.",
                disable_cancel_button=True,
            )
            return

        msg = "Select the textures that should be assigned to this material."

        def assign_texture(paths=None):
            if not paths:
                paths = texture_dict
            check_boxes = delegate.get_checkboxes()
            if check_boxes:
                checked_boxes = [box.name for key, box in check_boxes.items() if box.model.get_value_as_bool()]
            else:
                checked_boxes = []

            if not checked_boxes and self._dialog:
                self._dialog.hide()
                return

            with omni.kit.undo.group():
                for item in items:
                    for value_model in item.value_models:
                        display_name = value_model.attributes[0].GetName().replace("inputs:", "")
                        if checked_boxes and display_name not in checked_boxes:
                            continue
                        if display_name in paths:
                            value_model.block_set_value(False)
                            rel_path = omni.client.normalize_url(
                                usd.make_path_relative_to_current_edit_target(paths[display_name], stage=self._stage)
                            ).replace("\\", "/")
                            value_model.set_value(rel_path)

            if self._dialog:
                self._dialog.hide()

        # Allow for skipping the dialog, if needed
        if allow_dialog_skip:
            assign_texture()
            return

        base_height = 124
        for _ in range(len(texture_dict)):
            base_height += 24
        # Dialog to ask for one or all textures
        self._dialog = TextureDialog(
            "Texture Assignment",
            visible=True,
            width=500,
            height=400,
            dockPreference=ui.DockPreference.DISABLED,
            flags=(
                ui.WINDOW_FLAGS_NO_COLLAPSE
                | ui.WINDOW_FLAGS_NO_MOVE
                | ui.WINDOW_FLAGS_NO_RESIZE
                | ui.WINDOW_FLAGS_NO_CLOSE
                | ui.WINDOW_FLAGS_MODAL
                | ui.WINDOW_FLAGS_NO_SCROLLBAR
            ),
        )

        model = Model()
        for texture_type, texture_path in texture_dict.items():
            model.add_item(Path(texture_path).name, texture_type)
        delegate = Delegate()
        with self._dialog.frame:
            with ui.HStack(spacing=ui.Pixel(self._WIDGET_PADDING)):
                ui.Spacer(width=0)
                with ui.VStack(spacing=ui.Pixel(self._WIDGET_PADDING)):
                    ui.Spacer(height=0)
                    ui.Label(msg, height=0)
                    with ui.ZStack():
                        ui.Rectangle(name="TreePanelBackground")
                        with ui.VStack(spacing=ui.Pixel(self._WIDGET_PADDING)):
                            ui.Spacer(height=0)
                            with ui.ScrollingFrame(
                                name="PropertiesPaneSection",
                                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                            ):
                                texture_tree = ui.TreeView(
                                    model,
                                    delegate=delegate,
                                    root_visible=False,
                                    header_visible=False,
                                )
                                texture_tree.set_selection_changed_fn(model.set_items_selected)
                            ui.Spacer(height=0)

                    with ui.HStack(height=0, spacing=ui.Pixel(self._WIDGET_PADDING)):
                        ui.Spacer()
                        ui.Button(
                            text="Assign",
                            identifier="AssignButton",
                            clicked_fn=functools.partial(assign_texture),
                        )
                        ui.Button(text="Cancel", identifier="CancelButton", clicked_fn=self._dialog.hide)
                        ui.Spacer()
                    ui.Spacer(height=0)
                ui.Spacer(width=0)

    def __check_for_similar_textures(self):
        """
        Check if there are any textures of a similar basename and set those found.
        """

        def find_texture_set(paths: list[str]):
            items = self._material_properties_widget.property_model.get_all_items()
            paths = [Path(path) for path in paths]
            first_path = paths[0]
            basename = first_path.name
            for path_obj in first_path.parent.iterdir():
                if path_obj.is_file() and path_obj.suffix in _SUPPORTED_TEXTURE_EXTENSIONS and path_obj not in paths:
                    paths.append(path_obj)

            self._texture_assignment(paths, items, allow_dialog_skip=False, basename=basename)

        _open_file_picker(
            "Select Texture Set",
            find_texture_set,
            lambda *args: None,
            apply_button_label="Choose",
            file_extension_options=[("*.dds", "Compatible Textures")],
            allow_multi_selection=True,
        )

    def __ignore_warning_ingest_asset(self, callback, value):
        callback(value)

    def __check_asset_was_ingested_and_in_proj_dir(self, callback, value):
        layer = self._stage.GetEditTarget().GetLayer()
        try:
            abs_new_asset_path = omni.client.normalize_url(layer.ComputeAbsolutePath(value))
        except Exception:  # noqa.
            # It means that this is not a path (metadata?). Even if we check the type of the attribute, some item
            # use the attribute, but override the value (like when we set metadata).
            callback(value)
            return

        # If the file path is not in general valid, use callback and return
        if not self._asset_replacement_core.is_file_path_valid(abs_new_asset_path, layer, log_error=False):
            callback(value)
            return

        if not self._asset_replacement_core.was_the_asset_ingested(abs_new_asset_path):
            ingest_enabled = bool(
                omni.kit.app.get_app()
                .get_extension_manager()
                .get_enabled_extension_id("lightspeed.trex.control.ingestcraft")
            )
            _TrexMessageDialog(
                title=_constants.ASSET_NEED_INGEST_WINDOW_TITLE,
                message=_constants.ASSET_NEED_INGEST_MESSAGE,
                ok_handler=functools.partial(self.__ignore_warning_ingest_asset, callback, value),
                ok_label=_constants.ASSET_NEED_INGEST_WINDOW_OK_LABEL,
                disable_ok_button=not self._asset_replacement_core.asset_is_in_project_dir(
                    path=abs_new_asset_path, layer=layer
                ),
                disable_cancel_button=False,
                disable_middle_button=not ingest_enabled,
                middle_label=_constants.ASSET_NEED_INGEST_WINDOW_MIDDLE_LABEL,
                middle_handler=self._go_to_ingest_tab,
            )
            return
        if not self._asset_replacement_core.asset_is_in_project_dir(path=abs_new_asset_path, layer=layer):
            _TrexMessageDialog(
                title=_constants.ASSET_OUTSIDE_OF_PROJ_DIR_TITLE,
                message=_constants.ASSET_OUTSIDE_OF_PROJ_DIR_MESSAGE,
                disable_ok_button=False,
                ok_label=_constants.ASSET_OUTSIDE_OF_PROJ_DIR_OK_LABEL,
                ok_handler=functools.partial(
                    _copy_non_usd_asset,
                    context=self._context,
                    asset_path=abs_new_asset_path,
                    callback_func=callback,
                ),
                disable_middle_button=True,
                disable_cancel_button=False,
            )
            return
        callback(value)

    def __remove_material_override(self, prims: list[Usd.Prim]):
        with omni.kit.undo.group():
            for prim in prims:
                if self._has_material_override([prim]):
                    _ToolMaterialCore.remove_material_override(self._context_name, prim)

            self.__on_material_changed()

    def __new_material_override(self, mdl_file_name: str, prims: list[Usd.Prim]):
        with omni.kit.undo.group():
            for prim in prims:
                if self._has_material_override([prim]):
                    self.__remove_material_override([prim])
                _ToolMaterialCore.create_new_material_override(
                    self._context_name,
                    _constants.MATERIAL_OVERRIDE_PATH.format(prim_node=str(prim.GetPath())),
                    mdl_file_name,
                    mdl_file_name.split(".")[0],
                    prim,
                )

            self.__on_material_changed()

    def __convert_material(self, mdl_file_name: str, prims: list[Usd.Prim]):
        with omni.kit.undo.group():
            _ToolMaterialCore.convert_materials(prims, mdl_file_name, context_name=self._context_name)
            self.__on_material_changed()

    @staticmethod
    def _shorten_material_id_string(input_string: str, size: int, delimiter: str):
        """Give the most interesting part of a prim path"""
        if len(input_string) > size:
            input_string = input_string[-size:]
            # try not to crop in the middle of a parent...
            input_string = input_string.partition(delimiter)[-1] if delimiter in input_string else input_string
            return "..." + delimiter + input_string
        return input_string

    @staticmethod
    def _concat_list_to_string(items):
        return "\n".join([str(item) for item in items])

    def refresh(self, items: list[Usd.Prim]):
        """Items should be a list Usd.Prim from which materials can be derived."""

        def hide_properties():
            self._material_properties_widget.show(False)  # to disable the listener
            self._material_properties_frames[None].visible = True
            self._material_properties_frames[self.MAT_PROP_FRAME].visible = False
            self._set_material_label("None")
            self._set_material_mdl_label("")

        self._current_material_mdl_file = None
        self._current_single_material = None
        mdl_files: set[Path] = set()

        # Filter prims and handle prims with refs
        filtered_items = []
        for item in items:
            if not isinstance(item, Usd.Prim):
                continue

            # If instance prim, get and use the correlating mesh prim
            if _is_instance(item):
                prototype_prim = self._asset_replacement_core.get_corresponding_prototype_prims([item])
                if not prototype_prim:
                    continue
                item = self._stage.GetPrimAtPath(prototype_prim[0])
                if not item:
                    continue

            # If not a mat prim and has reference, refresh widget to clear
            if not _is_material_prototype(item) and _get_reference_file_paths(item)[1]:
                self.refresh([])

            # Add the item; Should be mat or mesh prim
            filtered_items.append(item)

        if not filtered_items:
            hide_properties()
            return

        # Gather materials
        materials = set()
        for prim in filtered_items:
            for mat in self._core.get_materials_from_prim(prim):
                materials.add(mat)
        materials = list(materials)

        if not materials:
            hide_properties()
            return

        # Build material property widget accordingly
        self._material_properties_frames[self.MAT_PROP_FRAME].visible = True
        self._material_properties_frames[None].visible = False

        for material in materials:
            material_prim = self._stage.GetPrimAtPath(material)
            shader_prim = omni.usd.get_shader_from_material(material_prim, True)
            if shader_prim:
                shader = UsdShade.Shader(shader_prim)
                source_asset = shader.GetSourceAsset("mdl") if shader else None
                if source_asset:
                    mdl_file = source_asset.resolvedPath
                    mdl_files.add(Path(mdl_file))

        asyncio.ensure_future(self._refresh_material_menu())
        self._material_properties_widget.show(True)
        # TODO: For multi-selection, properties are ordered by USD, not click-order in Stage Manager or Selection Tree.
        #  Displaying only one set of shared property values is not the best UX.
        self._material_properties_widget.refresh(materials)
        material_label_text = self._shorten_material_id_string(str(materials[0]), self.MATERIAL_LABEL_NAME_SIZE, "/")
        if len(materials) == 1:
            self._set_material_label(material_label_text)
            self._current_single_material = materials[0]
        else:
            multiple_info_text = f"Multiple Selected (editing all, displaying {material_label_text})"
            multiple_info_details = multiple_info_text + "\n\n" + SetupUI._concat_list_to_string(materials)
            self._set_material_label(multiple_info_text, tooltip=multiple_info_details)
            self._current_single_material = None

        mdl_file_label = "None"
        mdl_file_label_tooltip = ""
        if len(mdl_files) == 1:
            self._current_material_mdl_file = mdl_files.pop()
            mdl_file_label = self._current_material_mdl_file.name
            mdl_file_label_tooltip = str(self._current_material_mdl_file.absolute())
        elif len(mdl_files) > 1:
            mdl_file_label = "Multiple"
        self._set_material_mdl_label(mdl_file_label, tooltip=mdl_file_label_tooltip)

    def _set_material_label(self, label: str, tooltip=None):
        self._current_material_label.text = label
        self._current_material_label.tooltip = label if tooltip is None else tooltip

    def _set_material_mdl_label(self, label: str, tooltip=None):
        self._current_material_mdl_file_label.text = label
        self._current_material_mdl_file_label.tooltip = label if tooltip is None else tooltip

    def _has_material_override(self, prims: list[Usd.Prim]) -> bool:
        for prim in prims:
            rel = prim.GetRelationship(_constants.MATERIAL_RELATIONSHIP)
            if not rel.IsValid():
                continue
            targets = rel.GetForwardedTargets()
            for target in targets:
                stage = prim.GetStage()
                if targets and not omni.usd.check_ancestral(stage.GetPrimAtPath(target)):
                    return True
        return False

    @omni.usd.handle_exception
    async def _refresh_material_menu(self):
        # for instance materials, we allow the user to override the reference in stage
        def refresh_instance_items(prims, num_prims):
            if num_prims > 0:

                omni.ui.Separator(
                    text=" Override Material ("
                    + (prims[0].GetName() if num_prims == 1 else f"Multiple ({num_prims})")
                    + ") ",
                    tooltip=SetupUI._concat_list_to_string([prim.GetPath() for prim in prims]),
                )

                item = omni.ui.MenuItem(
                    "\tRemove Material Override",
                    visible=self._has_material_override(prims),
                    tooltip="Removes the material override instance (if it exists) from this specific object only.\n"
                    "This does not apply to shared materials.",
                )
                item.set_triggered_fn(partial(self.__remove_material_override, prims))
                item = omni.ui.MenuItem(
                    "\tCreate Material Override (Opaque)",
                    tooltip="Creates an opaque material override and applies to this prim only.\n"
                    "Unlike shared materials, this will create a new unique material for each selected object.",
                )
                item.set_triggered_fn(partial(self.__new_material_override, _constants.SHADER_NAME_OPAQUE, prims))
                item = omni.ui.MenuItem(
                    "\tCreate Material Override (Translucent)",
                    tooltip="Creates a translucent material override and applies to this prim only.\n"
                    "Unlike shared materials, this will create a new unique material for each selected object.",
                )
                item.set_triggered_fn(partial(self.__new_material_override, _constants.SHADER_NAME_TRANSLUCENT, prims))

        # for shared (i.e. capture) materials, we only show the ability to convert the material type
        async def refresh_shared_items(prims: list[Usd.Prim], num_prims: int):
            if num_prims > 0:
                omni.ui.Separator(
                    text=" Shared Material ("
                    + (prims[0].GetName() if num_prims == 1 else f"Multiple ({num_prims})")
                    + ") ",
                    tooltip=SetupUI._concat_list_to_string([prim.GetPath() for prim in prims]),
                )

                # only do conversion for materials when the conversion target type is different from the current type,
                # so we must separate the incoming prims into the two type buckets
                opaque_prims = []
                translucent_prims = []
                for p in prims:
                    prim_path = p.GetPath()
                    material_prims = _ToolMaterialCore.get_materials_from_prim_paths(
                        [prim_path], context_name=self._context_name
                    )
                    shaders = [usd.get_shader_from_material(material_prim) for material_prim in material_prims]
                    for shader in shaders:
                        identifier = await _ToolMaterialCore.get_shader_subidentifier(shader)
                        if identifier is None:
                            continue
                        if identifier == Path(_constants.SHADER_NAME_OPAQUE).stem:
                            opaque_prims.append(p)
                            break
                        if identifier == Path(_constants.SHADER_NAME_TRANSLUCENT).stem:
                            translucent_prims.append(p)
                            break

                item = omni.ui.MenuItem(
                    "\tConvert to Opaque",
                    enabled=bool(translucent_prims),
                    tooltip="Convert the selected shared material(s) to opaque (if not already opaque).\n"
                    "This will update all usages of this material, even if it's shared between multiple "
                    "objects.",
                )
                item.set_triggered_fn(
                    partial(self.__convert_material, _constants.SHADER_NAME_OPAQUE, translucent_prims)
                )
                item = omni.ui.MenuItem(
                    "\tConvert to Translucent",
                    enabled=bool(opaque_prims),
                    tooltip="Convert the selected shared material(s) to translucent (if not already translucent).\n"
                    "This will update all usages of this material, even if it's shared between multiple "
                    "objects.",
                )
                item.set_triggered_fn(
                    partial(self.__convert_material, _constants.SHADER_NAME_TRANSLUCENT, opaque_prims)
                )

        # menu_compatibility required to get tooltip and hide_on_click working
        self.__menu = omni.ui.Menu(menu_compatibility=False)
        with self.__menu:
            shared_material_items: list[Usd.Prim] = []
            instance_material_items: list[Usd.Prim] = []
            # sort prims into buckets with independent controls
            for prim in self._selected_prims:
                if _AssetReplacementsCore.prim_is_from_a_capture_reference(prim):
                    shared_material_items.append(prim)
                else:
                    instance_material_items.append(prim)
            # build the menus
            refresh_instance_items(instance_material_items, len(instance_material_items))
            await refresh_shared_items(shared_material_items, len(shared_material_items))
        self._texture_edit_status = False

    def _show_copy_menu(self, button):
        """
        Display a menu if the string field was right-clicked to show the copy full file path button.
        """
        # Only show the menu with right click
        if button != 1:
            return

        # NOTE: This menu is stored on the object to avoid garbage collection and being prematurely destroyed
        if self._context_menu is not None:
            self._context_menu.destroy()
        self._context_menu = ui.Menu("Context Menu")

        has_material_path = self._current_single_material is not None and str(self._current_single_material) != ""
        hash_match = None
        if has_material_path:
            hash_match = re.match(_constants.COMPILED_REGEX_HASH, self._current_single_material.pathString)
        with self._context_menu:
            ui.MenuItem(
                "Copy Material Path",
                enabled=has_material_path,
                identifier="copy_material_path",
                triggered_fn=lambda: omni.kit.clipboard.copy(self._current_single_material.pathString),
            )
            ui.MenuItem(
                "Copy Material Hash",
                enabled=hash_match is not None,
                identifier="copy_material_hash",
                triggered_fn=lambda: omni.kit.clipboard.copy(hash_match.group(3)),
            )
            ui.MenuItem(
                "Copy Material MDL Path",
                enabled=self._current_material_mdl_file is not None,
                identifier="copy_material_mdl_path",
                triggered_fn=lambda: omni.kit.clipboard.copy(str(self._current_material_mdl_file.absolute())),
            )

        self._context_menu.show()

    def show(self, value: bool):
        if value:
            self._stage = usd.get_context(self._context_name).get_stage()

        self._material_properties_widget.show(value)  # to disable the listener

    def subscribe_on_material_changed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self.__on_material_changed, function)

    def destroy(self):
        self._selected_prims = []
        if self._external_drag_and_drop:
            self._external_drag_and_drop.destroy()
            self._external_drag_and_drop = None
        _reset_default_attrs(self)
