import os
import omni
import carb
import time
import asyncio
import subprocess
from pxr import Gf
from pxr import UsdGeom
from pxr import UsdShade
from pxr import UsdUtils
from pxr import Sdf
from pxr import Usd
import omni.usd 
import tempfile

from omni import ui
import omni.ext
import omni.kit.menu.utils as omni_utils
from omni.kit.widget.layers.path_utils import PathUtils
from omni.kit.menu.utils import MenuItemDescription

from PIL import Image
import os.path


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
        if texture.lower().endswith(".dds") or texture.lower().endswith(".png"):
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
        carb.log_info("Upscaling: " + texture)
        # convert to png
        if texture.lower().endswith(".dds"):
            pngTexturePath = os.path.join(tempDir.name, originalTextureName + ".png")
            carb.log_info("  - converting to png, out: " + pngTexturePath)
            convertPngProcess = subprocess.Popen([nvttPath, texture,"--output" , pngTexturePath])
            convertPngProcess.wait()
            if not os.path.exists(pngTexturePath):
                try:
                    with Image.open(texture) as im:
                        im.save(pngTexturePath,"PNG")
                except NotImplementedError as e:
                    pass
        else:
            pngTexturePath = texture
        # perform upscale
        upscaledTexturePath = os.path.join(originalTexturePath, originalTextureName + "_upscaled4x.png")
        carb.log_info("  - running neural networks, out: " + upscaledTexturePath)
        upscaleProcess = subprocess.Popen([esrganToolPath, "-i", pngTexturePath, "-o", upscaledTexturePath])
        upscaleProcess.wait()
        # check for alpha channel
        try:
            with Image.open(pngTexturePath) as memoryImage:
                if memoryImage.mode == "RGBA":
                    alphaPath = os.path.join(tempDir.name, originalTextureName + "_alpha.png")
                    upscaledAlphaPath = os.path.join(tempDir.name, originalTextureName + "_upscaled4x_alpha.png")
                    memoryImage.split()[-1].save(alphaPath)
                    upscaleProcess = subprocess.Popen([esrganToolPath, "-i", alphaPath, "-o", upscaledAlphaPath])
                    upscaleProcess.wait()
                    with Image.open(upscaledAlphaPath).convert("L") as upscaledAlphaImage:
                        with Image.open(upscaledTexturePath) as upscaledMemoryImage:   
                            upscaledMemoryImage.putalpha(upscaledAlphaImage)
                            upscaledMemoryImage.save(upscaledTexturePath,"PNG")
        except FileNotFoundError as e:
            carb.log_info("File not found error!")
            pass
        # convert to DDS, and generate mips (note dont use the temp dir for this)
        carb.log_info("  - compressing and generating mips, out: " + outputTexture)
        compressMipProcess = subprocess.Popen([nvttPath, upscaledTexturePath, "--format", "bc7", "--output", outputTexture])
        compressMipProcess.wait()
        tempDir.cleanup()


    def __clicked(self): 
        # reset the upscale list
        self._texturesToUpscale.clear() 

        # get/setup layer
        stage = omni.usd.get_context().get_stage()

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

        autoUpscaleStagePath = os.path.join(os.path.dirname(omni.usd.get_context().get_stage_url()), 'autoupscale.usda')
        try:
            autoStage = Usd.Stage.Open(autoUpscaleStagePath)
        except:
            autoStage = Usd.Stage.CreateNew(autoUpscaleStagePath)
        autoStage.DefinePrim('/RootNode')
        autoStage.DefinePrim('/RootNode/Looks','Scope')

        for prim in stage.GetPrimAtPath('/RootNode/Looks').GetChildren():
            UsdShade.Material.Define(autoStage, prim.GetPath())
            originShader = prim.GetChild('Shader')
            shader = UsdShade.Shader.Define(autoStage, originShader.GetPath())
            Usd.ModelAPI(shader).SetKind('Material')
            shaderPrim = shader.GetPrim()
            attr = shaderPrim.CreateAttribute('inputs:diffuse_texture', Sdf.ValueTypeNames.Asset)
            attrOrigin = originShader.GetAttribute('inputs:diffuse_texture')
            pathOrigin = attrOrigin.Get().path
            attr.Set(pathOrigin.replace(os.path.splitext(pathOrigin)[1], '_upscaled4x.dds'))
            attr.SetColorSpace('auto')

        autoStage.GetRootLayer().Save()

        combinedStagePath = os.path.join(os.path.dirname(omni.usd.get_context().get_stage_url()), 'combined.usda')
        try:
            combinedStage = Usd.Stage.Open(combinedStagePath)
        except:
            combinedStage = Usd.Stage.CreateNew(combinedStagePath)

        # this property is supposed to be read-only, but the setter in the C++ lib are missing in the python lib
        combinedStage.GetRootLayer().subLayerPaths = [os.path.basename(autoUpscaleStagePath), os.path.basename(omni.usd.get_context().get_stage_url())]
        combinedStage.GetRootLayer().Save()
