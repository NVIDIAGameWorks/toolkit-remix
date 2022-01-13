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
from pxr import UsdShade
import omni.ui as ui
import omni.usd
from omni.kit.property.usd.custom_layout_helper import CustomLayoutFrame, CustomLayoutGroup, CustomLayoutProperty
from omni.kit.property.usd.usd_attribute_widget import UsdPropertiesWidget
from omni.kit.property.usd.references_widget import PayloadReferenceWidget
from omni.kit.property.usd.prim_selection_payload import PrimSelectionPayload
from omni.kit.property.material.scripts.usd_attribute_widget import UsdMaterialAttributeWidget
from lightspeed.common import constants


class MaterialAssetWidget(UsdMaterialAttributeWidget):
    def __init__(self, title: str):
        super().__init__(title=title, schema=UsdShade.Material, include_names=[], exclude_names=[])
        self._useful_attrs = {
            "inputs:anisotropy",
            "inputs:diffuse_color_constant",
            "inputs:diffuse_texture",
            "inputs:emissive_color",
            "inputs:emissive_color_constant",
            "inputs:emissive_intensity",
            "inputs:emissive_mask_texture",
            "inputs:enable_emission",
            "inputs:ior_constant",
            "inputs:metallic_constant",
            "inputs:metallic_texture",
            "inputs:normalmap_texture",
            "inputs:opacity_constant",
            "inputs:reflection_roughness_constant",
            "inputs:reflectionroughness_texture",
            "inputs:tangent_texture",
            "inputs:transmittance_color",
            "inputs:transmittance_measurement_distance",
        }

    def on_new_payload(self, payload):
        if len(payload) == 0:
            super().on_new_payload(payload)
            return False

        stage = payload.get_stage()
        instance_prims = []
        material_paths = []
        for p in payload:
            prim = stage.GetPrimAtPath(p)
            if prim.IsValid():
                if str(p).startswith(constants.INSTANCE_PATH):
                    references = prim.GetReferences()
                    refs_and_layers = omni.usd.get_composed_references_from_prim(prim)
                    for (ref, layer) in refs_and_layers:
                        if not ref.assetPath:
                            material, relationship = UsdShade.MaterialBindingAPI(
                                stage.GetPrimAtPath(ref.primPath)
                            ).ComputeBoundMaterial()
                            if material:
                                material_paths.append(material.GetPath())
                elif str(p).startswith(constants.MESH_PATH):
                    material, relationship = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
                    if material:
                        material_paths.append(material.GetPath())
                elif prim.IsA(UsdShade.Material):
                    material_paths.append(p)

        if not material_paths:
            return False

        super().on_new_payload(PrimSelectionPayload(weakref.ref(payload.get_stage()), material_paths))

        return True

    def _customize_props_layout(self, attrs):
        all_attrs = super()._customize_props_layout(attrs)
        return [attr for attr in all_attrs if attr.attr_name in self._useful_attrs]

    def build_items(self):
        ui.Label(
            "Modifying this material will affect all meshes using it.", name="label", alignment=ui.Alignment.LEFT_TOP
        )
        super().build_items()
