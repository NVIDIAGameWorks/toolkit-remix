"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import functools
import typing
from asyncio import ensure_future
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
from omni import kit, ui, usd
from omni.flux.properties_pane.materials.usd.widget import MaterialPropertyWidget as _MaterialPropertyWidget
from omni.flux.property_widget_builder.model.usd import utils as usd_properties_utils
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf

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

        self.__conversion_buttons_task = None

        self.__create_ui()

        self.__on_material_converted = _Event()
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
                        ui.Label(
                            "Material",
                            name="PropertiesWidgetLabel",
                            alignment=ui.Alignment.RIGHT_CENTER,
                            width=ui.Percent(self.COLUMN_WIDTH_PERCENT),
                        )
                        ui.Spacer(width=ui.Pixel(8), height=0)
                        self._frame_combobox_materials = ui.Frame()
                    ui.Spacer(height=ui.Pixel(8))
                    self._convert_opaque_button = ui.Button(
                        "Convert to Opaque",
                        height=ui.Pixel(32),
                        clicked_fn=partial(self.__convert_material, _constants.SHADER_NAME_OPAQUE),
                    )
                    self._convert_translucent_button = ui.Button(
                        "Convert to Translucent",
                        height=ui.Pixel(32),
                        clicked_fn=partial(self.__convert_material, _constants.SHADER_NAME_TRANSLUCENT),
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

    def __show_material(self, materials, model, _):
        current_index = model.get_item_value_model().as_int
        current_selection = materials[current_index]

        self.__update_conversion_buttons(usd.get_shader_from_material(self._stage.GetPrimAtPath(current_selection)))

        self._material_properties_widget.refresh([str(current_selection)])

    def __convert_material(self, mdl_file_name: str):
        _ToolMaterialCore.convert_materials(self._selected_prims, mdl_file_name, context_name=self._context_name)
        self.__on_material_converted()

    def __update_conversion_buttons(self, shader):
        if self.__conversion_buttons_task:
            self.__conversion_buttons_task.cancel()
        self.__conversion_buttons_task = ensure_future(
            kit.material.library.get_subidentifier_from_material(
                shader, on_complete_fn=self.__update_conversion_buttons_callback
            )
        )

    def __update_conversion_buttons_callback(self, identifiers: str):
        identifier = str(identifiers[0]) if identifiers else None

        if self._convert_opaque_button:
            self._convert_opaque_button.visible = identifier != Path(_constants.SHADER_NAME_OPAQUE).stem
        if self._convert_translucent_button:
            self._convert_translucent_button.visible = identifier != Path(_constants.SHADER_NAME_TRANSLUCENT).stem

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
        if not found:
            self._material_properties_frames[None].visible = True
        self._material_properties_widget.show(found)  # to disable the listener

        if found:
            # we select the material
            self._selected_prims = [item.prim for item in items if isinstance(item, _ItemPrim)]
            if self._selected_prims:
                # TODO: select only the first selection for now, and select the material that match the selected usd ref
                materials = self._core.get_materials_from_prim(self._selected_prims[0])
                if materials:
                    self._frame_combobox_materials.clear()
                    default_idx = 0
                    with self._frame_combobox_materials:
                        material_list_combobox = ui.ComboBox(
                            default_idx,
                            *[str(material) for material in materials],
                            style_type_name_override="PropertiesWidgetField",
                        )
                        material_list_combobox.model.add_item_changed_fn(partial(self.__show_material, materials))
                        self.__update_conversion_buttons(
                            usd.get_shader_from_material(self._stage.GetPrimAtPath(materials[default_idx]))
                        )
                    self._material_properties_widget.refresh([materials[default_idx]])
                    return
        self._material_properties_widget.show(False)  # to disable the listener
        self._material_properties_frames[None].visible = True
        self._material_properties_frames[_ItemPrim].visible = False

    def show(self, value):
        if value:
            self._stage = usd.get_context(self._context_name).get_stage()

        self._material_properties_widget.show(value)  # to disable the listener

    def subscribe_on_material_converted(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self.__on_material_converted, function)

    def destroy(self):
        self._selected_prims = None
        if self.__conversion_buttons_task:
            self.__conversion_buttons_task.cancel()
        self.__conversion_buttons_task = None
        _reset_default_attrs(self)
