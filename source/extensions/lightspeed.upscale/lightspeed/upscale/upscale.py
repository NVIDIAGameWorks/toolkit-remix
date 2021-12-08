import contextlib
import os
import os.path
import subprocess
import tempfile

import carb
import omni
import omni.ext
import omni.kit.menu.utils as omni_utils
import omni.usd
from omni.kit.menu.utils import MenuItemDescription
from PIL import Image
from pxr import Sdf, Tf, Usd, UsdShade, UsdUtils


class LightspeedUpscalerExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self.__create_save_menu()

    def __create_save_menu(self):
        self._tools_manager_menus = [
            MenuItemDescription(name="Upscale Game Textures", onclick_fn=self.__clicked, glyph="none.svg")
        ]
        omni_utils.add_menu_items(self._tools_manager_menus, "LSS")

    def on_shutdown(self):
        pass

    _textures_to_upscale = {}
    _current_layer = None

    def gather_textures(self, texture):
        if texture.lower().endswith(".dds") or texture.lower().endswith(".png"):
            upscaled_dds_texture_path = texture.replace(os.path.splitext(texture)[1], "_upscaled4x.dds")
            self._textures_to_upscale[texture] = upscaled_dds_texture_path
        return texture

    # todo: this should be async job!
    def perform_upscale(self, texture, output_texture):
        # setup script paths'
        if os.path.exists(output_texture):
            carb.log_info("Skipping " + texture + " since " + output_texture + " already exists.")
            return
        script_path = os.path.dirname(os.path.abspath(__file__))
        nvtt_path = script_path + ".\\tools\\nvtt\\nvtt_export.exe"
        esrgan_tool_path = script_path + ".\\tools\\realesrgan-ncnn-vulkan-20210901-windows\\realesrgan-ncnn-vulkan.exe"
        # create temp dir and get texture name/path
        original_texture_name = os.path.splitext(os.path.basename(texture))[0]
        output_texture_name = os.path.splitext(os.path.basename(output_texture))[0]
        output_texture_path = os.path.dirname(os.path.abspath(output_texture))
        temp_dir = tempfile.TemporaryDirectory()
        # begin real work
        carb.log_info("Upscaling: " + texture)
        # convert to png
        if texture.lower().endswith(".dds"):
            png_texture_path = os.path.join(temp_dir.name, original_texture_name + ".png")
            carb.log_info("  - converting to png, out: " + png_texture_path)
            convert_png_process = subprocess.Popen([nvtt_path, texture, "--output", png_texture_path])
            convert_png_process.wait()
            # use PILLOW as a fallback if nvtt fails
            if not os.path.exists(png_texture_path):
                with contextlib.suppress(NotImplementedError):
                    with Image.open(texture) as im:
                        im.save(png_texture_path, "PNG")
        else:
            png_texture_path = texture
        # perform upscale
        os.makedirs(os.path.dirname(output_texture), exist_ok=True)
        upscaled_texture_path = os.path.join(output_texture_path, output_texture_name + ".png")
        carb.log_info("  - running neural networks, out: " + upscaled_texture_path)
        upscale_process = subprocess.Popen([esrgan_tool_path, "-i", png_texture_path, "-o", upscaled_texture_path])
        upscale_process.wait()
        # check for alpha channel and upscale it if it exists
        try:
            with Image.open(png_texture_path) as memory_image:
                if memory_image.mode == "RGBA":
                    alpha_path = os.path.join(temp_dir.name, original_texture_name + "_alpha.png")
                    upscaled_alpha_path = os.path.join(temp_dir.name, original_texture_name + "_upscaled4x_alpha.png")
                    memory_image.split()[-1].save(alpha_path)
                    upscale_process = subprocess.Popen([esrgan_tool_path, "-i", alpha_path, "-o", upscaled_alpha_path])
                    upscale_process.wait()
                    with Image.open(upscaled_alpha_path).convert("L") as upscaled_alpha_image:
                        with Image.open(upscaled_texture_path) as upscaled_memory_image:
                            upscaled_memory_image.putalpha(upscaled_alpha_image)
                            upscaled_memory_image.save(upscaled_texture_path, "PNG")
        except FileNotFoundError:
            carb.log_info("File not found error!")
            pass
        # convert to DDS, and generate mips (note dont use the temp dir for this)
        carb.log_info("  - compressing and generating mips, out: " + output_texture)
        compress_mip_process = subprocess.Popen(
            [nvtt_path, upscaled_texture_path, "--format", "bc7", "--output", output_texture]
        )
        compress_mip_process.wait()
        temp_dir.cleanup()

    def __clicked(self):
        # reset the upscale list
        self._textures_to_upscale.clear()

        # get/setup layer
        stage = omni.usd.get_context().get_stage()

        # populate the texture list
        for stage_layer in [stage.GetRootLayer(), stage.GetSessionLayer()]:
            (all_layers, all_assets, unresolved_paths) = UsdUtils.ComputeAllDependencies(stage_layer.identifier)
            if not all_layers:
                all_layers = stage.GetLayerStack()

            for layer in all_layers:
                self._current_layer = layer
                UsdUtils.ModifyAssetPaths(layer, self.gather_textures)

        self._current_layer = None

        # perform upscale
        for original_tex, output_tex in self._textures_to_upscale.items():
            if not os.path.isabs(original_tex):
                # place the output textures next to the enhancements layer location
                output_tex_path = os.path.join(os.path.dirname(stage.GetRootLayer().subLayerPaths[0]), output_tex)
                capture_usd_directory = os.path.dirname(stage.GetRootLayer().subLayerPaths[-1])
                original_texture_path = os.path.join(capture_usd_directory, original_tex)
            else:
                output_tex_path = output_tex
                original_texture_path = original_tex
            self.perform_upscale(original_texture_path, output_tex_path)

        # create/open and populate auto-upscale layer, placing it next to the enhancements layer
        enhancement_usd_dir = os.path.dirname(stage.GetRootLayer().subLayerPaths[0])
        auto_upscale_stage_path = os.path.join(enhancement_usd_dir, "autoupscale.usda")
        try:
            auto_stage = Usd.Stage.Open(auto_upscale_stage_path)
        except Tf.ErrorException:
            auto_stage = Usd.Stage.CreateNew(auto_upscale_stage_path)
        auto_stage.DefinePrim("/RootNode")
        auto_stage.DefinePrim("/RootNode/Looks", "Scope")

        for prim in stage.GetPrimAtPath("/RootNode/Looks").GetChildren():
            UsdShade.Material.Define(auto_stage, prim.GetPath())
            origin_shader = prim.GetChild("Shader")
            shader = UsdShade.Shader.Define(auto_stage, origin_shader.GetPath())
            Usd.ModelAPI(shader).SetKind("Material")
            shader_prim = shader.GetPrim()
            attr = shader_prim.CreateAttribute("inputs:diffuse_texture", Sdf.ValueTypeNames.Asset)
            attr_origin = origin_shader.GetAttribute("inputs:diffuse_texture")
            path_origin = attr_origin.Get().path
            attr.Set(path_origin.replace(os.path.splitext(path_origin)[1], "_upscaled4x.dds"))
            attr.SetColorSpace("auto")

        auto_stage.GetRootLayer().Save()

        # add the auto-upscale layer to the workspace layer just above the capture layer
        # this property is supposed to be read-only, but the setter in the C++ lib are missing in the python lib
        if auto_upscale_stage_path not in stage.GetRootLayer().subLayerPaths:
            index_above_capture_usd = len(stage.GetRootLayer().subLayerPaths) - 1
            stage.GetRootLayer().subLayerPaths.insert(index_above_capture_usd, auto_upscale_stage_path)
