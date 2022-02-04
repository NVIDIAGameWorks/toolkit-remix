"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import carb
import weakref
from pxr import Usd, Sdf, UsdShade
import omni.ui as ui
import omni.usd
from omni.kit.property.usd.custom_layout_helper import CustomLayoutFrame, CustomLayoutGroup, CustomLayoutProperty
from omni.kit.property.usd.usd_attribute_widget import UsdPropertiesWidget
from omni.kit.property.usd.references_widget import PayloadReferenceWidget, DEFAULT_PRIM_TAG
from omni.kit.property.usd.prim_selection_payload import PrimSelectionPayload
from omni.kit.property.material.scripts.usd_attribute_widget import UsdMaterialAttributeWidget
from lightspeed.common import constants
from typing import Union


class MeshAssetWidget(PayloadReferenceWidget):
    def __init__(self, title: str):
        super().__init__()
        self._title = title
        self._correcting_prim_path = False

    def on_new_payload(self, payload):
        if len(payload) == 0:
            super().on_new_payload(payload)
            return False

        stage = payload.get_stage()
        instance_prims = []
        mesh_paths = []
        for p in payload:
            prim = stage.GetPrimAtPath(p)
            if prim.IsValid():
                if str(p).startswith(constants.INSTANCE_PATH):
                    instance_prims.append(prim)
                elif str(p).startswith(constants.MESH_PATH):
                    mesh_paths.append(p)

        # Get the mesh asset(s) for all selected instances
        for prim in instance_prims:
            references = prim.GetReferences()
            refs_and_layers = omni.usd.get_composed_references_from_prim(prim)
            for (ref, layer) in refs_and_layers:
                if not ref.assetPath:
                    mesh_paths.append(ref.primPath)

        super().on_new_payload(PrimSelectionPayload(weakref.ref(stage), mesh_paths))
        if not mesh_paths:
            return False
        return True

    def build_items(self):
        ui.Label(
            "Replacing this reference will affect all instances using this mesh.",
            name="label",
            alignment=ui.Alignment.LEFT_TOP,
        )
        super().build_items()

        
    def _on_payload_reference_edited(
        self, model_or_item, stage: Usd.Stage, prim_path: Sdf.Path, payref: Union[Sdf.Reference, Sdf.Payload], intro_layer: Sdf.Layer
    ):
        if self._correcting_prim_path:
            return

        new_asset_path = self._ref_dict[payref].asset_path_field.model.get_value_as_string()

        if str(payref.assetPath) != new_asset_path:
            self._correcting_prim_path = True
            self._ref_dict[payref].prim_path_field.model.set_value(DEFAULT_PRIM_TAG)
            self._correcting_prim_path = False

        super()._on_payload_reference_edited(model_or_item, stage, prim_path, payref, intro_layer)

