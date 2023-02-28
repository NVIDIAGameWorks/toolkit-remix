import asyncio
from pathlib import Path
from typing import List

import carb
import omni.ui as ui
import omni.usd
from lightspeed.common import constants
from lightspeed.error_popup.window import ErrorPopup
from lightspeed.layer_helpers import LightspeedTextureProcessingCore
from lightspeed.progress_popup.window import ProgressPopup
from lightspeed.upscale.core import UpscalerCore
from omni.kit.window.toolbar.widget_group import WidgetGroup
from pxr import UsdShade

from .core import ToolMaterialCore


class MaterialButtons:
    def __init__(self, force_material_paths: List[str] = None, enable_stage_event=False):
        """Add new tools in the toolbar:
        - Convert to Opaque Material
        - Convert to Translucent Material
        - Upscale all textures on selected materials
        """
        super().__init__()
        self._opaque_button = None
        self._translucent_button = None
        self._upscale_button = None
        self._core = ToolMaterialCore()
        self._upscale_progress_bar = None
        self._force_material_paths = [] if force_material_paths is None else force_material_paths
        self._stage_event = None
        if enable_stage_event:
            self._stage_event = (
                omni.usd.get_context()
                .get_stage_event_stream()
                .create_subscription_to_pop(self._on_stage_event, name="[lightspeed.tool.material] Stage Event")
            )

    def _on_stage_event(self, event):
        if event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            self.refresh_buttons_stat()

    def set_force_material_paths(self, paths: List[str]):
        self._force_material_paths = paths

    def clean(self):
        self._core = None
        self._upscale_progress_bar = None
        self._stage_event = None
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
            "_upscaled4x.png",
        )
        error = await LightspeedTextureProcessingCore.lss_async_batch_process_capture_layer_by_prim_paths(
            processing_config, material_prim_paths, progress_callback=self._material_upscale_set_progress
        )
        if error:
            self._error_popup = ErrorPopup("An error occurred while upscaling", error, window_size=(350, 150))
            self._error_popup.show()
        if self._upscale_progress_bar:
            self._upscale_progress_bar.hide()
            self._upscale_progress_bar = None

    def _on_opaque_clicked(self, *_):
        if not self._opaque_button.enabled:
            return
        self._opaque_button.checked = False

        select_prim_paths = (
            self._force_material_paths or omni.usd.get_context().get_selection().get_selected_prim_paths()
        )

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
        self._core.set_new_mdl_to_shaders(shaders, material_prims, stage, "AperturePBR_Opacity.mdl")

    def _on_translucent_clicked(self, *_):
        if not self._translucent_button.enabled:
            return
        self._translucent_button.checked = False

        select_prim_paths = (
            self._force_material_paths or omni.usd.get_context().get_selection().get_selected_prim_paths()
        )
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()

        material_prims = self._core.get_materials_from_prim_paths(select_prim_paths)
        shaders = [self._core.get_shader_from_material(material_prim) for material_prim in material_prims]
        shader_paths = [shader.GetPath() for shader in shaders]
        # check shaders in the current selection
        for select_prim_path in select_prim_paths:
            prim = stage.GetPrimAtPath(select_prim_path)
            if prim.IsValid() and prim.IsA(UsdShade.Shader) and UsdShade.Shader(prim).GetPath() not in shader_paths:
                shaders.append(UsdShade.Shader(prim))
                shader_paths.append(UsdShade.Shader(prim).GetPath())
        carb.log_info("Convert to Translucent Material for selection")
        carb.log_verbose(str(shaders))
        self._core.set_new_mdl_to_shaders(shaders, material_prims, stage, "AperturePBR_Translucent.mdl")

    def _on_upscale_clicked(self, *_):
        if not self._upscale_button.enabled:
            return
        select_prim_paths = (
            self._force_material_paths or omni.usd.get_context().get_selection().get_selected_prim_paths()
        )

        material_objects = self._core.get_materials_from_prim_paths(select_prim_paths)
        carb.log_info("Upscale textures on selected materials")

        material_prim_paths = []
        for material in material_objects:
            material_prim_paths.append(material.GetPrim().GetPath())
        asyncio.ensure_future(self._run_material_upscale(material_prim_paths))

    def refresh_buttons_stat(self):
        select_prim_paths = (
            self._force_material_paths or omni.usd.get_context().get_selection().get_selected_prim_paths()
        )
        material_prims = self._core.get_materials_from_prim_paths(select_prim_paths)
        to_enable = False
        for material_prim in material_prims:
            refs_and_layers = omni.usd.get_composed_references_from_prim(material_prim.GetPrim())
            if refs_and_layers:
                to_enable = True
                break
        if self._opaque_button:
            self._opaque_button.enabled = to_enable
        if self._translucent_button:
            self._translucent_button.enabled = to_enable
        if self._upscale_button:
            self._upscale_button.enabled = to_enable
        return to_enable  # noqa

    def create(self, default_size):
        self._opaque_button = ui.Button(
            name="opaqueMaterial",
            tooltip="Convert to Opaque Material",
            width=default_size,
            height=default_size,
            mouse_pressed_fn=self._on_opaque_clicked,
        )

        self._translucent_button = ui.Button(
            name="translucentMaterial",
            tooltip="Convert to Translucent Material",
            width=default_size,
            height=default_size,
            mouse_pressed_fn=self._on_translucent_clicked,
        )

        self._upscale_button = ui.Button(
            name="upscaleMaterial",
            tooltip="Upscale textures associated with the selected material(s) in the capture layer",
            width=default_size,
            height=default_size,
            mouse_pressed_fn=self._on_upscale_clicked,
        )
        self.refresh_buttons_stat()
        return {
            "opaqueMaterial": self._opaque_button,
            "translucentMaterial": self._translucent_button,
            "upscaleMaterial": self._upscale_button,
        }

    def _get_data_path(self):
        current_path = Path(__file__).parent
        for _ in range(3):
            current_path = current_path.parent
        return str(current_path.joinpath("data"))

    def get_style(self):
        """
        Gets the style of all widgets defined in this Widgets group.
        Subclassed
        """
        return {
            "Button.Image::opaqueMaterial": {"image_url": f"{self._get_data_path()}/toolbar_opaque_material.png"},
            "Button.Image::opaqueMaterial:disabled": {
                "image_url": f"{self._get_data_path()}/toolbar_opaque_material_disabled.png"
            },
            "Button.Image::translucentMaterial": {"image_url": f"{self._get_data_path()}/toolbar_glass_material.png"},
            "Button.Image::translucentMaterial:disabled": {
                "image_url": f"{self._get_data_path()}/toolbar_glass_material_disabled.png"
            },
            "Button.Image::upscaleMaterial": {"image_url": f"{self._get_data_path()}/toolbar_upscale_material.png"},
            "Button.Image::upscaleMaterial:disabled": {
                "image_url": f"{self._get_data_path()}/toolbar_upscale_material_disabled.png"
            },
        }


class MaterialButtonGroup(WidgetGroup):
    def __init__(self):
        super().__init__()
        self._button = MaterialButtons(enable_stage_event=True)

    def _on_opaque_clicked(self, *_):
        self._acquire_toolbar_context()
        super()._on_opaque_clicked(*_)

    def _on_translucent_clicked(self, *_):
        self._acquire_toolbar_context()
        super()._on_translucent_clicked(*_)

    def _on_upscale_clicked(self, *_):
        self._acquire_toolbar_context()
        super()._on_upscale_clicked(*_)

    def create(self, default_size):
        self._button.create(default_size)

    def get_style(self):
        """
        Gets the style of all widgets defined in this Widgets group.
        Subclassed
        """
        return self._button.get_style()

    def clean(self):
        self._button.clean()
        super().clean()
