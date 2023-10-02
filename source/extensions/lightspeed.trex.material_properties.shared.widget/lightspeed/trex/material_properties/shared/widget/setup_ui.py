"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio
import functools
import typing
from functools import partial
from pathlib import Path
from typing import List, Union

import omni.kit.app
from lightspeed.common import constants as _constants
from lightspeed.tool.material.core import ToolMaterialCore as _ToolMaterialCore
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.material.core.shared import Setup as _MaterialCore
from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import ItemPrim as _ItemPrim
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from omni import ui, usd
from omni.flux.properties_pane.materials.usd.widget import MaterialPropertyWidget as _MaterialPropertyWidget
from omni.flux.property_widget_builder.model.usd import utils as usd_properties_utils
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
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
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._asset_replacement_core = _AssetReplacementsCore(context_name)
        self._core = _MaterialCore(context_name)

        self._stage = usd.get_context(self._context_name).get_stage()

        self._selected_prims = []
        self._material_properties_frames = {}

        self.__create_ui()

        self.__on_material_changed = _Event()
        self.__on_go_to_ingest_tab = _Event()

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
                    self._material_properties_widget = _MaterialPropertyWidget(
                        self._context_name, tree_column_widths=[ui.Percent(self.COLUMN_WIDTH_PERCENT)]
                    )

        self._sub_on_material_refresh_done = self._material_properties_widget.subscribe_refresh_done(
            self._on_material_refresh_done
        )

    def _on_material_refresh_done(self):
        """
        Set callback that will check if an asset was ingested. For now we handle only Asset type (texture) from
        material
        """
        items = self._material_properties_widget.property_model.get_all_items()
        for item in items:
            for value_model in item.value_models:
                if usd_properties_utils.get_type_name(value_model.metadata) in [Sdf.ValueTypeNames.Asset]:
                    value_model.set_callback_pre_set_value(self.__check_asset_was_ingested)

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
        _reset_default_attrs(self)
