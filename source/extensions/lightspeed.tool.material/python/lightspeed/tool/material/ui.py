import asyncio

import carb
import omni.ui as ui
import omni.usd
from lightspeed.common import constants
from lightspeed.layer_manager import LightspeedTextureProcessingCore
from omni.kit.tool.collect.progress_popup import ProgressPopup
from omni.kit.window.toolbar.widget_group import WidgetGroup
from omni.upscale import UpscalerCore
from pxr import UsdShade

from .core import ToolMaterialCore


class MaterialButtonGroup(WidgetGroup):
    def __init__(self, _data_path):
        """Add new tools in the toolbar:
            - Convert to Opaque Material
            - Convert to Translucent Material
            - Upscale all textures on selected materials
        """
        super().__init__()
        self.__data_path = _data_path
        self._opaque_button = None
        self._translucent_button = None
        self._upscale_button = None
        self._core = ToolMaterialCore()
        self._upscale_progress_bar = None

    def clean(self):
        super().clean()
        self._opaque_button = None
        self._translucent_button = None
        self._upscale_button = None

    def _material_upscale_set_progress(self, progress):
        self._upscale_progress_bar.set_progress(progress)

    async def _run_material_upscale(self, material_prim_paths):
        if not self._upscale_progress_bar:
            self._upscale_progress_bar = ProgressPopup(title="Upscaling")
        self._upscale_progress_bar.set_progress(0)
        self._upscale_progress_bar.show()
        processing_config = (
            UpscalerCore.perform_upscale,
            constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
            constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
            "_upscaled4x.dds",
        )
        await LightspeedTextureProcessingCore.lss_async_batch_process_capture_layer_by_prim_paths(
            processing_config, material_prim_paths, progress_callback=self._material_upscale_set_progress
        )
        self._upscale_progress_bar.hide()
        self._upscale_progress_bar = None

    def create(self, default_size):
        def on_opaque_clicked(*_):
            self._acquire_toolbar_context()
            self._opaque_button.checked = False

            select_prim_paths = omni.usd.get_context().get_selection().get_selected_prim_paths()

            usd_context = omni.usd.get_context()
            stage = usd_context.get_stage()

            material_prims = self._core.get_materials_from_prim_paths(select_prim_paths)
            shaders = [self._core.get_shader_from_material(material_prim) for material_prim in material_prims]
            # check shaders in the current selection
            for select_prim_path in select_prim_paths:
                prim = stage.GetPrimAtPath(select_prim_path)
                if prim.IsValid() and prim.IsA(UsdShade.Shader):
                    shaders.append(UsdShade.Shader(prim))
            carb.log_info("Convert to Opaque Material for selection")
            carb.log_verbose(str(shaders))
            self._core.set_new_mdl_to_shaders(shaders, "AperturePBR_Opacity.mdl")

        def on_translucent_clicked(*_):
            self._acquire_toolbar_context()
            self._translucent_button.checked = False

            select_prim_paths = omni.usd.get_context().get_selection().get_selected_prim_paths()

            usd_context = omni.usd.get_context()
            stage = usd_context.get_stage()

            material_prims = self._core.get_materials_from_prim_paths(select_prim_paths)
            shaders = [self._core.get_shader_from_material(material_prim) for material_prim in material_prims]
            # check shaders in the current selection
            for select_prim_path in select_prim_paths:
                prim = stage.GetPrimAtPath(select_prim_path)
                if prim.IsValid() and prim.IsA(UsdShade.Shader):
                    shaders.append(UsdShade.Shader(prim))
            carb.log_info("Convert to Translucent Material for selection")
            carb.log_verbose(str(shaders))
            self._core.set_new_mdl_to_shaders(shaders, "AperturePBR_Translucent.mdl")

        def on_upscale_clicked(*_):
            self._acquire_toolbar_context()

            select_prim_paths = omni.usd.get_context().get_selection().get_selected_prim_paths()

            material_objects = self._core.get_materials_from_prim_paths(select_prim_paths)
            carb.log_info("Upscale textures on selected materials")

            material_prim_paths = []
            for material in material_objects:
                material_prim_paths.append(material.GetPrim().GetPath())
            asyncio.ensure_future(self._run_material_upscale(material_prim_paths))

        self._opaque_button = ui.Button(
            name="opaqueMaterial",
            tooltip="Convert to Opaque Material",
            width=default_size,
            height=default_size,
            mouse_pressed_fn=on_opaque_clicked,
        )

        self._translucent_button = ui.Button(
            name="translucentMaterial",
            tooltip="Convert to Translucent Material",
            width=default_size,
            height=default_size,
            mouse_pressed_fn=on_translucent_clicked,
        )

        self._upscale_button = ui.Button(
            name="upscaleMaterial",
            tooltip="Upscale textures associated with the selected material(s) in the capture layer",
            width=default_size,
            height=default_size,
            mouse_pressed_fn=on_upscale_clicked,
        )
        return {
            "opaqueMaterial": self._opaque_button,
            "translucentMaterial": self._translucent_button,
            "upscaleMaterial": self._upscale_button,
        }

    def get_style(self):
        """
        Gets the style of all widgets defined in this Widgets group.
        Subclassed
        """
        return {
            "Button.Image::opaqueMaterial": {"image_url": f"{self.__data_path}/toolbar_opaque_material.png"},
            "Button.Image::translucentMaterial": {"image_url": f"{self.__data_path}/toolbar_glass_material.png"},
            "Button.Image::upscaleMaterial": {"image_url": f"{self.__data_path}/toolbar_upscale_material.png"},
        }
