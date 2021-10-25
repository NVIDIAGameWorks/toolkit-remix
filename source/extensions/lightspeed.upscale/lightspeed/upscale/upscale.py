import os
import omni
import carb
import time
import asyncio
import subprocess
from pxr import Gf
from pxr import UsdGeom
from pxr import UsdUtils
from pxr import Sdf
import omni.usd
import tempfile

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

    # todo: this should be async job!
    def perform_upscale(self, texture):
        if not path.lower().endswith(".dds"):
            return path
        # setup script paths
        script_path = os.path.dirname(os.path.abspath( __file__ ))
        nvttPath = script_path+".\\tools\\nvtt\\nvtt_export.exe"
        esrganToolPath = script_path+".\\tools\\realesrgan-ncnn-vulkan-20210901-windows\\realesrgan-ncnn-vulkan.exe"
        # create temp dir and get texture name/path
        originalTextureName = os.path.splitext(os.path.basename(texture))[0]
        originalTexturePath = os.path.dirname(os.path.abspath(texture))
        tempDir = tempfile.TemporaryDirectory(dir = "C:/temp")
        # begin real work
        print("Upscaling: " + texture)
        # convert to png
        pngTexturePath = os.path.join(tempDir.name, originalTextureName + ".png")
        print("  - converting to png, out: " + pngTexturePath)
        command = nvttPath + " " + texture + " --output " + pngTexturePath
        convertPngProcess = subprocess.Popen(command.split())
        convertPngProcess.wait()
        # perform upscale
        upscaledTexturePath = os.path.join(tempDir.name, originalTextureName + "_upscaled4x.png")
        print("  - running neural networks, out: " + upscaledTexturePath)
        command = esrganToolPath + " -i " + pngTexturePath + " -o " + upscaledTexturePath
        upscaleProcess = subprocess.Popen(command.split())
        upscaleProcess.wait()
        # convert to DDS, and generate mips (note dont use the temp dir for this)
        upscaledDDSTexturePath = os.path.join(originalTexturePath, originalTextureName + "_upscaled4x.dds")
        print("  - compressing and generating mips, out: " + upscaledDDSTexturePath)
        command = nvttPath + " " + upscaledTexturePath + " --format bc7 --output " + upscaledDDSTexturePath
        compressMipProcess = subprocess.Popen(command.split())
        compressMipProcess.wait()
        # destroy temp dir
        tempDir.cleanup()
        return upscaledDDSTexturePath

    def __clicked(self):
        stage = omni.usd.get_context().get_stage()

        # get the replacements layer (or create if not exist)
        replacementsLayer = Sdf.Layer.Find("replacements.usda")
        if replacementsLayer is None:
            replacementsLayer = Sdf.Layer.CreateNew("replacements.usda")

        # insert overs in the replacements layer for all textures returned in 'gather'
        stage.SetEditTarget(replacementsLayer)

        for stage_layer in [stage.GetRootLayer(), stage.GetSessionLayer()]:
            (all_layers, all_assets, unresolved_paths) = UsdUtils.ComputeAllDependencies(
                stage_layer.identifier
            )
            if not all_layers:
                all_layers = stage.GetLayerStack()

            for layer in all_layers:
                UsdUtils.ModifyAssetPaths(layer, perform_upscale)

        # revert to the original layer again when done
        stage.SetEditTarget(stage.GetRootLayer())
