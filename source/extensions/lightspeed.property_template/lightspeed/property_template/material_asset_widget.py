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
from lightspeed.tool.material.widget import MaterialButtons
from omni.kit.property.material.scripts.usd_attribute_widget import UsdMaterialAttributeWidget
from omni.kit.property.usd.prim_selection_payload import PrimSelectionPayload
from omni.kit.property.usd.usd_property_widget import UsdPropertiesWidget
from pxr import Usd, UsdGeom, UsdShade


class MaterialAssetWidget(UsdMaterialAttributeWidget):
    def __init__(self, title: str, materials: list, extension_path: str, parent_widget: "MaterialAssetsWidget"):
        super().__init__(title=title, schema=UsdShade.Material, include_names=[], exclude_names=[])
        self._extension_path = extension_path
        self._material_paths = materials
        self.__parent_widget = parent_widget  # noqa PLW0238
        self._current_material_index = 0
        self._button = MaterialButtons()
        self._style = {
            "Image::material": {"image_url": f"{self._extension_path}/icons/material@3x.png"},
            "Image::find": {"image_url": f"{self._extension_path}/icons/find.png"},
        }

    def on_new_payload(self, payload):

        self._current_material_index = 0

        if len(payload) == 0:
            super().on_new_payload(payload)
            return False

        material_path = None
        stage = payload.get_stage()
        prim = stage.GetPrimAtPath(payload[0])
        if prim.IsValid():
            material_path = payload[0]

        if material_path is None:
            return False

        current_material = self._material_paths[self._current_material_index]
        self._button.set_force_material_paths([str(current_material)])

        return super().on_new_payload(
            PrimSelectionPayload(weakref.ref(payload.get_stage()), [] if material_path is None else [material_path])
        )

    def clean(self):
        self.__parent_widget = None  # noqa PLW0238
        self._button.clean()
        super().clean()

    @property
    def title(self):
        return str(self._title)

    def show_material(self, model, item):
        if not self._payload:
            return
        current_index = model.get_item_value_model().as_int
        current_selection = self._material_paths[current_index]
        self._current_material_index = current_index
        self._button.set_force_material_paths([str(current_selection)])
        super().on_new_payload(PrimSelectionPayload(weakref.ref(self._payload.get_stage()), [current_selection]))
        self.request_rebuild()

    def _select_material(self, button):
        if button != 0:
            return
        current_material = self._material_paths[self._current_material_index]
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths([str(current_material)], True)

    def build_items(self):
        # self._collapsable_frame.name = "Frame"  # to have dark background
        with ui.VStack(spacing=8):
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
            with ui.CollapsableFrame(title="Tools", collapsed=False, height=0, style=self._button.get_style()):
                with ui.HStack(spacing=8):
                    self._button.create(48)
            super().build_items()


class MaterialAssetsWidget(UsdPropertiesWidget):
    def __init__(self, title: str, extension_path: str):
        super().__init__(title=title, collapsed=False)
        self.__children_widgets = []
        self.__extension_path = extension_path
        self.__prototypes_data = {}

    def on_new_payload(self, payloads):
        self.__prototypes_data = {}
        self.__children_widgets = []

        def get_mat_from_geo(prim, prototype):
            if prim.IsA(UsdGeom.Subset) or prim.IsA(UsdGeom.Mesh):
                material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
                if material:
                    mat_path = material.GetPath()
                    if mat_path not in self.__prototypes_data[str(prototype)]:
                        self.__prototypes_data[str(prototype)].append(mat_path)

        if len(payloads) == 0:
            super().on_new_payload(payloads)
            return False

        stage = payloads.get_stage()
        for p in payloads:  # noqa PLR1702
            prim = stage.GetPrimAtPath(p)
            if prim.IsValid():
                refs_and_layers = omni.usd.get_composed_references_from_prim(prim)
                if refs_and_layers:
                    for (ref, _layer) in refs_and_layers:
                        original_mesh = None
                        if not ref.assetPath:
                            original_mesh = str(ref.primPath)
                            if original_mesh not in self.__prototypes_data:
                                self.__prototypes_data[original_mesh] = []
                        elif str(p).startswith(constants.MESH_PATH):
                            original_mesh = str(p)
                            self.__prototypes_data[original_mesh] = []

                        if original_mesh is not None:  # original mesh
                            # we grab all children
                            prim_mesh = stage.GetPrimAtPath(original_mesh)
                            if prim_mesh.IsValid():
                                display_predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
                                children_iterator = iter(Usd.PrimRange(prim_mesh, display_predicate))
                                for child_prim in children_iterator:
                                    get_mat_from_geo(child_prim, original_mesh)

        if not self.__prototypes_data:
            return False

        for proto, materials in self.__prototypes_data.items():
            widget = MaterialAssetWidget(proto, materials, self.__extension_path, self)
            widget.on_new_payload(PrimSelectionPayload(weakref.ref(stage), materials[:1]))

            self.__children_widgets.append(widget)
        return True

    def build_items(self):
        self._collapsable_frame.name = "groupFrame"  # to have dark background
        with ui.VStack(spacing=8):
            for widget in self.__children_widgets:
                widget.build_impl()

    def clean(self):
        for children_widget in self.__children_widgets:
            children_widget.clean()
        self.__children_widgets = []
        super().clean()
