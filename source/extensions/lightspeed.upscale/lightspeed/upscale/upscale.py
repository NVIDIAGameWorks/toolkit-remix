import os
import omni
import carb
import time
import asyncio
from pxr import Gf
from pxr import UsdGeom
from pxr import UsdUtils

#from realesrgan import RealESRGANer

from omni import ui
import omni.ext
import omni.kit.menu.utils as omni_utils

from omni.kit.menu.utils import MenuItemDescription


class LightspeedUpscalerExtension(omni.ext.IExt):

    def on_startup(self, ext_id):
        self.__create_save_menu()

    def __create_save_menu(self):
        self._tools_manager_menus = [
            MenuItemDescription(
                name="Upscale Game Textures", onclick_fn=self.__clicked, glyph="none.svg"
            )
        ]
        omni_utils.add_menu_items(self._tools_manager_menus, "LSS")

    def on_shutdown(self):
        pass

    def __clicked(self):
        stage = omni.usd.get_context().get_stage()
        for stage_layer in [stage.GetRootLayer(), stage.GetSessionLayer()]:
            (all_layers, all_assets, unresolved_paths) = UsdUtils.ComputeAllDependencies(
                stage_layer.identifier
            )
            if not all_layers:
                all_layers = stage.GetLayerStack()
            for asset in all_assets:
                if(asset.lower().endswith(".dds")):
                    print(asset)