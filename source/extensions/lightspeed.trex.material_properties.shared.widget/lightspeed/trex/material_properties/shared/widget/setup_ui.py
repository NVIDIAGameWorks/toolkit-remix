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
from typing import List, Union

import omni.ui as ui
from lightspeed.trex.material.core.shared import Setup as _MaterialCore
from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import ItemPrim as _ItemPrim
from omni.flux.properties_pane.materials.usd.widget import MaterialPropertyWidget as _MaterialPropertyWidget
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
    from lightspeed.trex.selection_tree.shared.widget.selection_tree.model import (
        ItemReferenceFileMesh as _ItemReferenceFileMesh,
    )


class SetupUI:
    def __init__(self, context_name: str):
        """Nvidia StageCraft Viewport UI"""

        self._default_attr = {
            "_core": None,
            "_frame_none": None,
            "_material_properties_frames": None,
            "_none_provider_label": None,
            "_frame_material_widget": None,
            "_material_properties_widget": None,
            "_frame_combobox_materials": None,
            "_material_choice_label": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._core = _MaterialCore(context_name)
        self._material_properties_frames = {}
        self.__create_ui()

    def __create_ui(self):
        with ui.ZStack():
            self._frame_none = ui.Frame(visible=True)
            self._material_properties_frames[None] = self._frame_none
            with self._frame_none:
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(8))
                    with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                        ui.Spacer(height=0)
                        with ui.VStack(width=0):
                            ui.Spacer()
                            self._none_provider_label, _, _ = _create_label_with_font(
                                "None", "PropertiesWidgetLabel", remove_offset=False
                            )
                            ui.Spacer()
                        ui.Spacer(height=0)
            self._frame_material_widget = ui.Frame(visible=False)
            self._material_properties_frames[_ItemPrim] = self._frame_material_widget

            with self._frame_material_widget:
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(8))
                    with ui.HStack(height=ui.Pixel(24), spacing=8):
                        with ui.HStack(width=ui.Pixel(160)):
                            ui.Spacer()
                            with ui.VStack(width=0):
                                ui.Spacer()
                                self._material_choice_label, _, _ = _create_label_with_font(
                                    "Material", "PropertiesWidgetLabel", remove_offset=False
                                )
                                ui.Spacer()
                            ui.Spacer(width=0)
                        self._frame_combobox_materials = ui.Frame()
                    ui.Spacer(height=ui.Pixel(8))
                    self._material_properties_widget = _MaterialPropertyWidget(
                        self._context_name, tree_column_widths=[ui.Pixel(160)]
                    )

    def show_material(self, materials, model, item):
        current_index = model.get_item_value_model().as_int
        current_selection = materials[current_index]
        self._material_properties_widget.refresh([str(current_selection)])

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
            selected_prims = [item.prim for item in items if isinstance(item, _ItemPrim)]
            if selected_prims:
                # TODO: select only the first selection for now, and select the material that match the selected usd ref
                materials = self._core.get_materials_from_prim(selected_prims[0])
                if materials:
                    self._frame_combobox_materials.clear()
                    default_idx = 0
                    with self._frame_combobox_materials:
                        material_list_combobox = ui.ComboBox(default_idx, *[str(material) for material in materials])
                        material_list_combobox.model.add_item_changed_fn(
                            functools.partial(self.show_material, materials)
                        )
                    self._material_properties_widget.refresh([materials[default_idx]])
                    return
        self._material_properties_widget.show(False)  # to disable the listener
        self._material_properties_frames[None].visible = True
        self._material_properties_frames[_ItemPrim].visible = False

    def show(self, value):
        self._material_properties_widget.show(value)  # to disable the listener

    def destroy(self):
        _reset_default_attrs(self)
