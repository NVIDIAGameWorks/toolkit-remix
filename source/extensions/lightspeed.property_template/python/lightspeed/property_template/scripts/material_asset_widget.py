"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import weakref

import omni.ui as ui
import omni.usd
from lightspeed.common import constants
from omni.kit.property.material.scripts.usd_attribute_widget import UsdMaterialAttributeWidget
from omni.kit.property.usd.prim_selection_payload import PrimSelectionPayload
from pxr import Usd, UsdGeom, UsdShade


class MaterialAssetWidget(UsdMaterialAttributeWidget):
    def __init__(self, title: str, extension_path: str):
        super().__init__(title=title, schema=UsdShade.Material, include_names=[], exclude_names=[])
        self._extension_path = extension_path
        self._material_paths = []
        self._current_material_index = 0
        self._style = {
            "Image::material": {"image_url": f"{self._extension_path}/icons/material@3x.png"},
            "Image::find": {"image_url": f"{self._extension_path}/icons/find.png"},
        }

    def on_new_payload(self, payload):

        self._material_paths = []
        self._current_material_index = 0

        def get_mat_from_geo(prim):
            if prim.IsA(UsdGeom.Subset) or prim.IsA(UsdGeom.Mesh):
                material, relationship = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
                if material:
                    mat_path = material.GetPath()
                    if mat_path not in self._material_paths:
                        self._material_paths.append(mat_path)

        if len(payload) == 0:
            super().on_new_payload(payload)
            return False

        stage = payload.get_stage()
        for p in payload:
            prim = stage.GetPrimAtPath(p)
            if prim.IsValid():
                refs_and_layers = omni.usd.get_composed_references_from_prim(prim)
                if str(p).startswith(constants.INSTANCE_PATH) and refs_and_layers:
                    for (ref, _layer) in refs_and_layers:
                        if ref.primPath:  # original mesh
                            # we grab all children
                            prim_mesh = stage.GetPrimAtPath(ref.primPath)
                            if prim_mesh.IsValid():
                                display_predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
                                children_iterator = iter(Usd.PrimRange(prim_mesh, display_predicate))
                                for child_prim in children_iterator:
                                    get_mat_from_geo(child_prim)
                elif prim.IsA(UsdShade.Material):
                    self._material_paths.append(p)
                else:
                    display_predicate = Usd.TraverseInstanceProxies(Usd.PrimDefaultPredicate)
                    children_iterator = iter(Usd.PrimRange(prim, display_predicate))
                    for child in children_iterator:
                        get_mat_from_geo(child)

        if not self._material_paths:
            return False

        return super().on_new_payload(PrimSelectionPayload(weakref.ref(payload.get_stage()), self._material_paths[:1]))

    def show_material(self, model, item):
        if not self._payload:
            return
        current_index = model.get_item_value_model().as_int
        current_selection = self._material_paths[current_index]
        self._current_material_index = current_index
        super().on_new_payload(PrimSelectionPayload(weakref.ref(self._payload.get_stage()), [current_selection]))
        self.request_rebuild()

    def _select_material(self, b):
        if b != 0:
            return
        current_material = self._material_paths[self._current_material_index]
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths([str(current_material)], True)

    def build_items(self):
        with ui.CollapsableFrame(title="Current material", collapsed=False, height=0, style=self._style):
            with ui.HStack(spacing=8):
                ui.Image(width=96, height=96, fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT, name="material")
                with ui.VStack(spacing=8):
                    ui.Label(
                        "Modifying this material will affect all meshes using it.",
                        name="label",
                        alignment=ui.Alignment.LEFT_TOP,
                    )
                    with ui.HStack(spacing=8):
                        material_list_combobox = ui.ComboBox(
                            self._current_material_index, *[str(entry) for entry in self._material_paths]
                        )
                        material_list_combobox.model.add_item_changed_fn(self.show_material)
                        ui.Image(
                            width=20,
                            height=20,
                            fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                            name="find",
                            tooltip="Select the material",
                            mouse_pressed_fn=lambda x, y, b, m: self._select_material(b),
                        )
                    ui.Spacer()
        super().build_items()
