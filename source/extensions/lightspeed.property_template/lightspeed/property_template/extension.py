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
import omni.ext
import omni.kit.app
import omni.kit.window.property

from .asset_delegate import AssetDelegate
from .info_asset_widget import InfoAssetWidget
from .layer_delegate import LayerDelegate
from .material_asset_widget import MaterialAssetsWidget
from .mesh_asset_widget import MeshAssetsWidget


class PropertyTemplateExtension(omni.ext.IExt):
    """Standard extension support class, necessary for extension management"""

    def __init__(self, *args, **kwargs):
        super(PropertyTemplateExtension, self).__init__(*args, **kwargs)
        self._registered = False

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.property_template] Lightspeed Property Template startup")
        self._extension_path = omni.kit.app.get_app().get_extension_manager().get_extension_path(ext_id)
        property_window = omni.kit.window.property.get_window()
        if property_window:
            property_window.register_widget("prim", "lss_info_asset", InfoAssetWidget("Current selection information"))
            property_window.register_widget("prim", "lss_mesh_assets", MeshAssetsWidget("Shared Mesh"))
            property_window.register_widget(
                "prim", "lss_material_asset", MaterialAssetsWidget("Shared Material", self._extension_path)
            )
            property_window.register_scheme_delegate("prim", "lss_asset", AssetDelegate())
            property_window.register_scheme_delegate("layers", "lss_layer", LayerDelegate())
            property_window.set_scheme_delegate_layout("prim", ["lss_asset", "lss_layer"])
            self._registered = True

    def on_shutdown(self):
        carb.log_info("[lightspeed.property_template] Lightspeed Property Template shutdown")
        property_window = omni.kit.window.property.get_window()
        if self._registered and property_window:
            property_window.unregister_scheme_delegate("prim", "lss_asset")
            property_window.unregister_scheme_delegate("prim", "lss_layer")
            property_window.unregister_widget("prim", "lss_material_asset")
            property_window.unregister_widget("prim", "lss_mesh_assets")
            property_window.unregister_widget("prim", "lss_info_asset")
            self._registered = False
