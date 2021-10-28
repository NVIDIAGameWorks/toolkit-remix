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
from omni.kit.widget.layers.path_utils import PathUtils
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

    _texturesToUpscale = dict()
    _currentLayer = None

    def gather_textures(self, texture):
        if texture.lower().endswith(".dds"):
            absolute_tex_path = PathUtils.compute_absolute_path(self._currentLayer.identifier, texture)
            originalTextureName = os.path.splitext(os.path.basename(absolute_tex_path))[0]
            originalTexturePath = os.path.dirname(os.path.abspath(absolute_tex_path))
            upscaledDDSTexturePath = os.path.join(originalTexturePath, originalTextureName + "_upscaled4x.dds")
            self._texturesToUpscale[absolute_tex_path] = upscaledDDSTexturePath
        return texture

    def apply_upscaled_textures(self, texture):
        absolute_tex_path = PathUtils.compute_absolute_path(self._currentLayer.identifier, texture)
        if absolute_tex_path in self._texturesToUpscale:
            return self._texturesToUpscale[absolute_tex_path]
        return texture  

    # todo: this should be async job!
    def perform_upscale(self, texture, outputTexture):
        # setup script paths
        script_path = os.path.dirname(os.path.abspath( __file__ ))
        nvttPath = script_path+".\\tools\\nvtt\\nvtt_export.exe"
        esrganToolPath = script_path+".\\tools\\realesrgan-ncnn-vulkan-20210901-windows\\realesrgan-ncnn-vulkan.exe"
        # create temp dir and get texture name/path
        originalTextureName = os.path.splitext(os.path.basename(texture))[0]
        originalTexturePath = os.path.dirname(os.path.abspath(texture))
        tempDir = tempfile.TemporaryDirectory()
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
        print("  - compressing and generating mips, out: " + outputTexture)
        command = nvttPath + " " + upscaledTexturePath + " --format bc7 --output " + outputTexture
        compressMipProcess = subprocess.Popen(command.split())
        compressMipProcess.wait()
        # destroy temp dir
        tempDir.cleanup()


    def __clicked(self):
        # reset the upscale list
        self._texturesToUpscale.clear()

        # get/setup layer
        stage = omni.usd.get_context().get_stage()
        sublayer = Sdf.Layer.Find("replacements.usda")
        if sublayer is None:
            sublayer = Sdf.Layer.CreateNew("replacements.usda")
            omni.kit.commands.execute(
                "CreateSublayer",
                layer_identifier=stage.GetRootLayer().identifier,
                sublayer_position=0,
                new_layer_path=sublayer.identifier,
                transfer_root_content=False,
                create_or_insert=True,
            )

        # populate the texture list
        for stage_layer in [stage.GetRootLayer(), stage.GetSessionLayer()]:
            (all_layers, all_assets, unresolved_paths) = UsdUtils.ComputeAllDependencies(
                stage_layer.identifier
            )
            if not all_layers:
                all_layers = stage.GetLayerStack()

            for layer in all_layers:
                self._currentLayer = layer
                UsdUtils.ModifyAssetPaths(layer, self.gather_textures)

        self._currentLayer = None

        # perform upscale
        for originalTex, outputTex in self._texturesToUpscale.items():
            self.perform_upscale(originalTex, outputTex)

        # modify stuff in the new layer?
        omni.kit.commands.execute("SetEditTarget", layer_identifier=sublayer.identifier)

        # populate the texture list
        for stage_layer in [stage.GetRootLayer(), stage.GetSessionLayer()]:
            (all_layers, all_assets, unresolved_paths) = UsdUtils.ComputeAllDependencies(
                stage_layer.identifier
            )
            if not all_layers:
                all_layers = stage.GetLayerStack()

            for layer in all_layers:
                self._currentLayer = layer
                UsdUtils.ModifyAssetPaths(layer, self.apply_upscaled_textures)

        # revert to the original layer again when done
        omni.kit.commands.execute("SetEditTarget", layer_identifier=stage.GetRootLayer().identifier)
