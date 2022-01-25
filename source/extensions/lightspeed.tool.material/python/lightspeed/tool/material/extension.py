"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
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
import omni.kit.window.toolbar

from .ui import MaterialButtonGroup


class LightspeedSetupExtension(omni.ext.IExt):
    def __init__(self, *args, **kwargs):
        self._material_tools = None

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.tool.material] Lightspeed Tool Material startup")
        extension_path = omni.kit.app.get_app().get_extension_manager().get_extension_path(ext_id)

        toolbar = omni.kit.window.toolbar.toolbar.get_instance()
        # add material tools
        self._material_tools = MaterialButtonGroup(f"{extension_path}/data")
        toolbar.add_widget(self._material_tools, 100)

    def on_shutdown(self):
        carb.log_info("[lightspeed.tool.material] Lightspeed Tool Material startup")
        # cleanup the toolbar
        toolbar = omni.kit.window.toolbar.toolbar.get_instance()
        if toolbar and self._material_tools:
            toolbar.remove_widget(self._material_tools)
        self._material_tools = None
