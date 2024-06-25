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
import functools
import re
import typing
from functools import partial
from pathlib import Path
from typing import List, Union

import omni.client
import omni.kit.app
from lightspeed.common import constants as _constants
from lightspeed.tool.material.core import ToolMaterialCore as _ToolMaterialCore
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.contexts import get_instance as _trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as _Contexts
from lightspeed.trex.material.core.shared import Setup as _MaterialCore
from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import ItemPrim as _ItemPrim
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from omni import ui, usd
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS as _SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.asset_importer.core.data_models import (
    TEXTURE_TYPE_CONVERTED_SUFFIX_MAP as _TEXTURE_TYPE_CONVERTED_SUFFIX_MAP,
)
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP as _TEXTURE_TYPE_INPUT_MAP
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_REGEX_MAP as _TEXTURE_TYPE_REGEX_MAP
from omni.flux.asset_importer.core.data_models import TextureTypes as _TextureTypes
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
from pxr import Sdf, Usd

if typing.TYPE_CHECKING:
    from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import (
        ItemAddNewReferenceFileMesh as _ItemAddNewReferenceFileMesh,
    )
    from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import ItemInstanceMesh as _ItemInstanceMesh
    from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import (
        ItemInstancesMeshGroup as _ItemInstancesMeshGroup,
    )
    from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import ItemMesh as _ItemMesh
    from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import (
        ItemReferenceFileMesh as _ItemReferenceFileMesh,
    )


class TextureDialog(ui.Window):
    def hide(self):
        self.visible = False


class SetupUI:

    COLUMN_WIDTH_PERCENT = 40

    def __init__(self, context_name: str):
        """Nvidia StageCraft Viewport UI"""

        self._default_attr = {
            "_context_name": None,
            "_core": None,
            "_stage": None,
            "_frame_none": None,
            "_material_properties_frames": None,
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

        self._selected_prims = []
        self._material_properties_frames = {}

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
            builder = _FileTexturePicker(file_extension_options=[("*.dds", "Compatible Textures")])
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
            self._material_properties_frames[_ItemPrim] = self._frame_material_widget

            with self._frame_material_widget:
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(8))
                    with ui.HStack(height=ui.Pixel(24)):
                        ui.Spacer(width=ui.Pixel(50), height=0)
                        ui.Label(
                            "Material:",
                            name="PropertiesWidgetLabel",
                            alignment=ui.Alignment.RIGHT_CENTER,
                            width=ui.Pixel(30),
                        )
                        ui.Spacer(width=ui.Pixel(8), height=0)
                        with ui.ZStack(width=ui.Percent(60)):
                            ui.Rectangle(width=ui.Percent(100))
                            with ui.HStack(height=ui.Pixel(24)):
                                ui.Spacer(width=ui.Pixel(8), height=0)
                                self._current_material_label = ui.Label(
                                    "",
                                    name="PropertiesWidgetLabel",
                                    alignment=ui.Alignment.LEFT_CENTER,
                                    tooltip="",
                                    width=ui.Percent(80),
                                )
                        ui.Image(
                            "",
                            name="MenuBurger",
                            height=ui.Pixel(24),
                            mouse_pressed_fn=lambda x, y, b, m: self.__show_material_menu(),
                        )
                    ui.Spacer(height=ui.Pixel(8))
                    with ui.HStack(height=ui.Pixel(10)):
                        ui.Spacer(width=ui.Pixel(50), height=0)
                        ui.Button(
                            text="Assign Texture Sets",
                            name="AssignTextureSetButton",
                            clicked_fn=self.__check_for_similar_textures,
                            height=ui.Pixel(8),
                            width=ui.Pixel(12),
                        )
                    ui.Spacer(height=ui.Pixel(8))
                    self._material_properties_widget = _MaterialPropertyWidget(
                        self._context_name,
                        tree_column_widths=[ui.Percent(self.COLUMN_WIDTH_PERCENT)],
                        create_color_space_attributes=False,
                        field_builders=self.get_custom_field_builders(),
                    )

        self._sub_on_material_refresh_done = self._material_properties_widget.subscribe_refresh_done(
            self._on_material_refresh_done
        )

    def _drop_texture(self, event: _ExternalDragDrop, payload: List[str]):
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
        dropped_paths = []
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
                basename = path.stem

        other_dds_paths = dropped_paths[0].parent.glob("*.[dD][dD][sS]")
        self._texture_assignment(
            dropped_paths, items, allow_dialog_skip=False, basename=basename, found_paths=other_dds_paths
        )

    def _on_material_refresh_done(self):
        """
        Set callback that will check if an asset was ingested. For now, we handle only Asset type (texture) from
        material. And setting callback for setting texture edit status.
        """
        items = self._material_properties_widget.property_model.get_all_items()
        for item in items:
            for value_model in item.value_models:
                if usd_properties_utils.get_type_name(value_model.metadata) in [Sdf.ValueTypeNames.Asset]:
                    value_model.set_callback_pre_set_value(self.__check_asset_was_ingested)

    def __check_texture_basename(self, texture_type, basename, texture_stem):
        """
        Use texture regexes to compare against the basename.
        """
        if _TEXTURE_TYPE_REGEX_MAP.get(texture_type) is None:
            return False

        normal_types = [_TextureTypes.NORMAL_OGL, _TextureTypes.NORMAL_DX, _TextureTypes.NORMAL_OTH]
        if texture_type in normal_types:
            regex = rf".*({'|'.join([_TEXTURE_TYPE_REGEX_MAP.get(t) for t in normal_types])})"
        else:
            regex = rf".*({_TEXTURE_TYPE_REGEX_MAP.get(texture_type)})"

        # To make sure we don't trip up on 'Metal', make sure we check string starting at the end
        if texture_type == _TextureTypes.METALLIC:
            match = re.search(rf"{regex}$", texture_stem, re.IGNORECASE)
        else:
            match = re.search(regex, texture_stem, re.IGNORECASE)
        if match and basename:
            group = match.groups()[0] if len(match.groups()) > 0 else match.group(0)
            texture_base = texture_stem.split(group)[0]
            if texture_base in basename:
                return True

        return False

    @staticmethod
    def _parse_texture_paths(paths_to_update, required_ext="dds"):
        parsed_paths = {}
        for path in paths_to_update:
            name = path.name
            if not name.endswith(required_ext):
                continue
            # Split the string at underscores or periods
            parts = re.split(r"[_. -]", name)
            # Initialize an empty list to hold the final parts of the string
            parsed_parts = []

            # Iterate over each part split by underscore
            for part in parts:
                # Further split each part by capital letters, but keep the capital letters as part of the next word
                sub_parts = re.split("(?<=[a-z])(?=[A-Z])", part)
                parsed_parts.extend(sub_parts)
            parsed_paths[path] = parsed_parts
        return parsed_paths

    def _texture_assignment(self, selected_paths, items, allow_dialog_skip=True, basename=None, found_paths=None):
        """
        Sort textures before updating the texture fields. Show a dialog to give options before
        updating to confirm the user's intention.
        """
        texture_dict = {}

        def get_common_prefix(*lists):
            """Given any number of lists, returns the common elements starting from index=0."""
            if not lists:
                return []
            # Find the length of the shortest list to avoid index out of range errors
            min_length = min((len(lst) for lst in lists))
            # Initialize an empty list to store common elements
            common_elements = []
            # Iterate over the indices of the shortest list
            for idx in range(min_length):
                # Use the first list's element at index idx as a reference
                reference_element = lists[0][idx]
                # Check if all lists have the same element at index idx
                if all((lst[idx] == reference_element for lst in lists)):
                    # If all elements match, append the reference element to common_elements
                    common_elements.append(reference_element)
                else:
                    # If any element does not match, break the loop
                    break
            # Return the list of common elements
            return common_elements

        parsed_selections = self._parse_texture_paths(selected_paths)
        parsed_paths = self._parse_texture_paths(found_paths)
        # If there is more than one selection, find the common prefix
        pp = [list(val) for val in parsed_selections.values()]
        common_select = get_common_prefix(*pp)
        scores = [
            (path, len(get_common_prefix(common_select, path_parts))) for path, path_parts in parsed_paths.items()
        ]
        if scores:
            hi_score = max(val[1] for val in scores)
            similar_textures = [score[0] for score in scores if score[1] == hi_score]
        else:
            hi_score = -1
            similar_textures = []

        for similar_texture in similar_textures:
            sim_path = " ".join(parsed_paths.get(similar_texture, [])[hi_score:])
            for texture_type, pattern in _TEXTURE_TYPE_REGEX_MAP.items():
                if not pattern:
                    continue
                if re.search(pattern, sim_path, re.IGNORECASE):
                    texture_dict[_TEXTURE_TYPE_INPUT_MAP.get(texture_type)] = similar_texture

        for path in selected_paths:
            if path.suffix != ".dds":
                continue
            if len(path.stem.split(".")) > 1:
                trex_tag = path.stem.split(".")[-2]
                stem = path.stem.split(".")[:-2][0]
            else:
                trex_tag = ""
                stem = path.stem
            texture_type = _TEXTURE_TYPE_CONVERTED_SUFFIX_MAP.get(trex_tag, None)
            if texture_type:
                name = _TEXTURE_TYPE_INPUT_MAP[texture_type]
                if basename and not self.__check_texture_basename(texture_type, basename, stem):
                    continue
                texture_dict[name] = path

        if not texture_dict:
            return

        msg = "Would you like to assign any of the found textures?"

        def assign_texture(check_boxes=None, paths=None):
            if not paths:
                paths = texture_dict
            if check_boxes:
                checked_boxes = [box.name for box in check_boxes if box.model.get_value_as_bool()]
            else:
                checked_boxes = []
            with omni.kit.undo.group():
                for item in items:
                    for value_model in item.value_models:
                        display_name = value_model.attributes[0].GetName()
                        if checked_boxes and display_name not in checked_boxes:
                            continue
                        if display_name in paths:
                            rel_path = omni.client.normalize_url(
                                usd.make_path_relative_to_current_edit_target(
                                    str(paths[display_name]), stage=self._stage
                                )
                            ).replace("\\", "/")
                            value_model.set_value(rel_path)

            self._dialog.hide()

        # Allow for skipping the dialog, if needed
        if allow_dialog_skip:
            assign_texture()
            return

        # Dialog to ask for one or all textures
        self._dialog = TextureDialog(
            "Texture Assignment",
            visible=True,
            width=550,
            height=250,
            dockPreference=ui.DockPreference.DISABLED,
            flags=(
                ui.WINDOW_FLAGS_NO_COLLAPSE
                | ui.WINDOW_FLAGS_NO_MOVE
                | ui.WINDOW_FLAGS_NO_RESIZE
                | ui.WINDOW_FLAGS_NO_CLOSE
                | ui.WINDOW_FLAGS_MODAL
            ),
        )

        checkboxes = []
        with self._dialog.frame:
            with ui.VStack():
                ui.Label(msg)
                ui.Spacer(width=0, height=ui.Pixel(25))
                for name, texture in texture_dict.items():
                    with ui.HStack(height=ui.Pixel(25)):
                        ui.Label(texture.stem)
                        checkbox = ui.CheckBox()
                        checkbox.model.set_value(True)
                        checkbox.name = name
                        checkboxes.append(checkbox)
                ui.Spacer(width=0, height=ui.Pixel(8))
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(200), height=0)
                    ui.Button(
                        text="Assign",
                        name="AssignButton",
                        clicked_fn=functools.partial(assign_texture, checkboxes),
                        width=75,
                        height=30,
                    )
                    ui.Button(text="Cancel", name="CancelButton", clicked_fn=self._dialog.hide, width=75, height=30)

    def __check_for_similar_textures(self):
        """
        Check if there are any textures of a similar basename and set those found.
        """

        def find_texture_set(paths):
            items = self._material_properties_widget.property_model.get_all_items()
            paths = [Path(path) for path in paths]
            basename = paths[0].stem
            textures = []
            for path_obj in paths[0].parent.iterdir():
                if path_obj.is_file() and path_obj.suffix in _SUPPORTED_TEXTURE_EXTENSIONS and path_obj not in paths:
                    textures.append(path_obj)

            self._texture_assignment(paths, items, allow_dialog_skip=False, basename=basename, found_paths=textures)

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

    def __check_asset_was_ingested(self, callback, value):
        layer = self._stage.GetEditTarget().GetLayer()
        try:
            abs_new_asset_path = omni.client.normalize_url(layer.ComputeAbsolutePath(value))
        except Exception:  # noqa.
            # It means that this is not a path (metadata?). Even if we check the type of the attribute, some item
            # use the attribute, but override the value (like when we set metadata).
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
                disable_cancel_button=False,
                disable_middle_button=not ingest_enabled,
                middle_label=_constants.ASSET_NEED_INGEST_WINDOW_MIDDLE_LABEL,
                middle_handler=self._go_to_ingest_tab,
            )
            return
        callback(value)

    def __remove_material_override(self, prims: List[Usd.Prim]):
        with omni.kit.undo.group():
            for prim in prims:
                if self._has_material_override([prim]):
                    _ToolMaterialCore.remove_material_override(self._context_name, prim)

            self.__on_material_changed()

    def __new_material_override(self, mdl_file_name: str, prims: List[Usd.Prim]):
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

    def __convert_material(self, mdl_file_name: str, prims: List[Usd.Prim]):
        with omni.kit.undo.group():
            _ToolMaterialCore.convert_materials(prims, mdl_file_name, context_name=self._context_name)
            self.__on_material_changed()

    @staticmethod
    def _shorten_string(input_string, size, delimiter):
        return input_string[-size:].partition(delimiter)[-1] if delimiter in input_string else input_string

    @staticmethod
    def _concat_list_to_string(items):
        return "\n".join([str(item) for item in items])

    def refresh(
        self,
        items: List[
            Union[
                "_ItemMesh",
                "_ItemReferenceFileMesh",
                "_ItemAddNewReferenceFileMesh",
                "_ItemInstancesMeshGroup",
                "_ItemInstanceMesh",
                _ItemPrim,
            ]
        ],
    ):
        found = False
        for item_type, frame in self._material_properties_frames.items():
            if item_type is None:
                self._material_properties_frames[None].visible = False
                continue
            value = any(isinstance(item, item_type) for item in items) if items else False
            frame.visible = value
            if value:
                found = True

        if found:
            # we select the material
            self._selected_prims = [item.prim for item in items if isinstance(item, _ItemPrim)]
            if self._selected_prims:
                materials = set()
                for prim in self._selected_prims or []:
                    for mat in self._core.get_materials_from_prim(prim):
                        materials.add(mat)
                materials = list(materials)
                if materials:
                    asyncio.ensure_future(self._refresh_material_menu())
                    if len(materials) == 1:
                        # when we have just one material available, show properties
                        self._material_properties_widget.show(True)
                        self._material_properties_widget.refresh(materials)
                        self._set_material_label(str(materials[0]))
                    else:
                        # hide properties when multiple prims selected as this isnt supported yet
                        self._material_properties_widget.show(False)  # to disable the listener
                        self._set_material_label("Multiple Selected", SetupUI._concat_list_to_string(materials))

                    return
        self._material_properties_widget.show(False)  # to disable the listener
        self._material_properties_frames[None].visible = True
        self._material_properties_frames[_ItemPrim].visible = False
        self._set_material_label("None")

    def _set_material_label(self, label, tooltip=None):
        self._current_material_label.text = SetupUI._shorten_string(label, 32, "/")
        self._current_material_label.tooltip = label if tooltip is None else tooltip

    def _has_material_override(self, prims: List[Usd.Prim]) -> bool:
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
        async def refresh_shared_items(prims, num_prims):
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
            shared_material_items = []
            instance_material_items = []
            # sort prims into buckets with independent controls
            for prim in self._selected_prims or []:
                if _AssetReplacementsCore.prim_is_from_a_capture_reference(prim):
                    shared_material_items.append(prim)
                else:
                    instance_material_items.append(prim)
            # build the menus
            refresh_instance_items(instance_material_items, len(instance_material_items))
            await refresh_shared_items(shared_material_items, len(shared_material_items))
        self._texture_edit_status = False

    def show(self, value):
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
        self._selected_prims = None
        if self._external_drag_and_drop:
            self._external_drag_and_drop.destroy()
            self._external_drag_and_drop = None
        _reset_default_attrs(self)
