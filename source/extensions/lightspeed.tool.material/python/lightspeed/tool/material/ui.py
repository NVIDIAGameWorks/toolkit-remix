import carb
import omni.ui as ui
import omni.usd
from lightspeed.upscale import LightspeedUpscalerCore
from omni.kit.window.toolbar.widget_group import WidgetGroup
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

    def clean(self):
        super().clean()
        self._opaque_button = None
        self._translucent_button = None
        self._upscale_button = None

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
            self._upscale_button.checked = False

            select_prim_paths = omni.usd.get_context().get_selection().get_selected_prim_paths()

            usd_context = omni.usd.get_context()
            stage = usd_context.get_stage()

            material_objects = self._core.get_materials_from_prim_paths(select_prim_paths)
            carb.log_info("Upscale textures on selected materials")

            material_prims = []
            for material in material_objects:
                material_prims.append(material.GetPrim())
            LightspeedUpscalerCore.batch_upscale_capture_layer(material_prims)
            
        self._opaque_button = ui.ToolButton(
            name="opaqueMaterial",
            tooltip="Convert to Opaque Material",
            width=default_size,
            height=default_size,
            mouse_pressed_fn=on_opaque_clicked,
        )

        self._translucent_button = ui.ToolButton(
            name="translucentMaterial",
            tooltip="Convert to Translucent Material",
            width=default_size,
            height=default_size,
            mouse_pressed_fn=on_translucent_clicked,
        )
        
        self._upscale_button = ui.ToolButton(
            name="upscaleMaterial",
            tooltip="Upscale textures associated with the selected material(s) in the capture layer",
            width=default_size,
            height=default_size,
            mouse_pressed_fn=on_upscale_clicked,
        )
        return {"opaqueMaterial": self._opaque_button, "translucentMaterial": self._translucent_button, "upscaleMaterial": self._upscale_button}

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
