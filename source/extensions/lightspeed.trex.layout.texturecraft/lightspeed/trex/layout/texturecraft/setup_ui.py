"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio
import functools
import os
from enum import Enum

import omni.ui as ui
import omni.usd
from lightspeed.color_to_normal.core import ColorToNormalCore
from lightspeed.color_to_roughness.core import ColorToRoughnessCore
from lightspeed.common import constants
from lightspeed.error_popup.window import ErrorPopup
from lightspeed.layer_helpers import LightspeedTextureProcessingCore
from lightspeed.progress_popup.window import ProgressPopup
from lightspeed.trex.contexts.setup import Contexts as TrexContexts
from lightspeed.trex.layout.shared import SetupUI as ReplicatorLayout
from lightspeed.upscale.core import UpscaleModels, UpscalerCore


class UpscaleProcessConfig(Enum):
    ESRGAN_DEFAULT = (
        functools.partial(UpscalerCore.perform_upscale, UpscaleModels.ESRGAN.value),
        constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
        constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
        "_upscaled4x.png",
    )
    ESRGAN_OVERWRITE = (
        functools.partial(UpscalerCore.perform_upscale, UpscaleModels.ESRGAN.value, overwrite=True),
        constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
        constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
        "_upscaled4x.png",
    )
    SR3_DEFAULT = (
        functools.partial(UpscalerCore.perform_upscale, UpscaleModels.SR3.value),
        constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
        constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
        "_upscaled4x.png",
    )
    SR3_OVERWRITE = (
        functools.partial(UpscalerCore.perform_upscale, UpscaleModels.SR3.value, overwrite=True),
        constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
        constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
        "_upscaled4x.png",
    )


class ColorToNormalProcessConfig(Enum):
    DEFAULT = (
        ColorToNormalCore.perform_conversion,
        constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
        constants.MATERIAL_INPUTS_NORMALMAP_TEXTURE,
        "_color2normal.png",
    )
    OVERWRITE = (
        functools.partial(ColorToNormalCore.perform_conversion, overwrite=True),
        constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
        constants.MATERIAL_INPUTS_NORMALMAP_TEXTURE,
        "_color2normal.png",
    )


class ColorToRoughnessProcessConfig(Enum):
    DEFAULT = (
        ColorToRoughnessCore.perform_conversion,
        constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
        constants.MATERIAL_INPUTS_REFLECTIONROUGHNESS_TEXTURE,
        "_color2roughness.png",
    )
    OVERWRITE = (
        functools.partial(ColorToRoughnessCore.perform_conversion, overwrite=True),
        constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
        constants.MATERIAL_INPUTS_REFLECTIONROUGHNESS_TEXTURE,
        "_color2roughness.png",
    )


class SetupUI(ReplicatorLayout):
    DEFAULT_HEIGHT = 180
    PADDING = 16

    def __init__(self, ext_id):
        super().__init__(ext_id)
        self.__run_batch_task = None

        self._upscale_models = [UpscaleModels.ESRGAN.value.name]
        if os.getenv(constants.REMIX_ENV_INTERNAL):
            self._upscale_models = [UpscaleModels.SR3.value.name, *self._upscale_models]
        self._selected_model = 0

    @property
    def default_attr(self):
        default_attr = super().default_attr
        default_attr.update(
            {
                "_progress_bar": None,
                "_error_popup": None,
            }
        )
        return default_attr

    def __update_selected_upscale_model(self, model, *_):
        self._selected_model = model.get_item_value_model().get_value_as_int()

    def __on_upscale_clicked(self, override: bool):
        if self._selected_model == 0:
            config = UpscaleProcessConfig.SR3_OVERWRITE.value if override else UpscaleProcessConfig.SR3_DEFAULT.value
        else:
            config = (
                UpscaleProcessConfig.ESRGAN_OVERWRITE.value if override else UpscaleProcessConfig.ESRGAN_DEFAULT.value
            )

        self._run_batch(self._deferred_run_batch, config)

    def _create_layout(self):
        with ui.VStack():
            ui.Label("Texture Craft: temporary tool", alignment=ui.Alignment.CENTER, height=50, name="Title0")
            ui.Label(
                'Those tools will create an "autoupscale" layer with enhanced textures',
                alignment=ui.Alignment.CENTER,
                height=50,
                name="Warning",
            )
            with ui.HStack():
                ui.Spacer(width=ui.Pixel(self.PADDING))
                with ui.ZStack(height=ui.Pixel(self.DEFAULT_HEIGHT)):
                    ui.Rectangle(name="WorkspaceBackground")
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8))
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))
                            ui.Label("Upscale", name="Title1", alignment=ui.Alignment.CENTER, height=0)
                            with ui.VStack():
                                ui.Label(
                                    "Upscale all textures in the current capture layer",
                                    height=ui.Pixel(32),
                                    alignment=ui.Alignment.CENTER,
                                )
                                ui.Spacer(height=ui.Pixel(8))

                                model_selection_combobox = ui.ComboBox(self._selected_model, *self._upscale_models)
                                model_selection_combobox.model.add_item_changed_fn(self.__update_selected_upscale_model)

                                ui.Spacer(width=ui.Pixel(0))

                                ui.Button(
                                    "Skip already converted textures",
                                    height=ui.Pixel(32),
                                    clicked_fn=functools.partial(self.__on_upscale_clicked, False),
                                )
                                ui.Button(
                                    "Overwrite all textures (re-convert everything)",
                                    height=ui.Pixel(32),
                                    clicked_fn=functools.partial(self.__on_upscale_clicked, True),
                                )

                            ui.Spacer(height=ui.Pixel(8))
                        ui.Spacer(width=ui.Pixel(8))
                ui.Spacer(width=ui.Pixel(self.PADDING))
                with ui.ZStack(height=ui.Pixel(self.DEFAULT_HEIGHT)):
                    ui.Rectangle(name="WorkspaceBackground")
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8))
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))
                            ui.Label("Color to normal", alignment=ui.Alignment.CENTER, name="Title1", height=0)
                            with ui.VStack():
                                ui.Label(
                                    "Generate Normal Maps from all textures in the current capture layer",
                                    height=ui.Pixel(50),
                                    alignment=ui.Alignment.CENTER,
                                )
                                ui.Spacer(width=0)
                                ui.Button(
                                    "Skip already converted textures",
                                    height=ui.Pixel(32),
                                    clicked_fn=functools.partial(
                                        self._run_batch,
                                        self._deferred_run_batch,
                                        ColorToNormalProcessConfig.DEFAULT.value,
                                    ),
                                )
                                ui.Button(
                                    "Overwrite all textures (re-convert everything)",
                                    height=ui.Pixel(32),
                                    clicked_fn=functools.partial(
                                        self._run_batch,
                                        self._deferred_run_batch,
                                        ColorToNormalProcessConfig.OVERWRITE.value,
                                    ),
                                )

                            ui.Spacer(height=ui.Pixel(8))
                        ui.Spacer(width=ui.Pixel(8))
                ui.Spacer(width=ui.Pixel(self.PADDING))
                with ui.ZStack(height=ui.Pixel(self.DEFAULT_HEIGHT)):
                    ui.Rectangle(name="WorkspaceBackground")
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8))
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))
                            ui.Label("Color to roughness", alignment=ui.Alignment.CENTER, name="Title1", height=0)
                            with ui.VStack():
                                ui.Label(
                                    "Generate Roughness Maps from all the textures in the current capture layer",
                                    height=ui.Pixel(50),
                                    alignment=ui.Alignment.CENTER,
                                )
                                ui.Spacer(width=0)
                                ui.Button(
                                    "Skip already converted textures",
                                    height=ui.Pixel(32),
                                    clicked_fn=functools.partial(
                                        self._run_batch,
                                        self._deferred_run_batch,
                                        ColorToRoughnessProcessConfig.DEFAULT.value,
                                    ),
                                )
                                ui.Button(
                                    "Overwrite all textures (re-convert everything)",
                                    height=ui.Pixel(32),
                                    clicked_fn=functools.partial(
                                        self._run_batch,
                                        self._deferred_run_batch,
                                        ColorToRoughnessProcessConfig.OVERWRITE.value,
                                    ),
                                )
                            ui.Spacer(height=ui.Pixel(8))
                        ui.Spacer(width=ui.Pixel(8))
                ui.Spacer(width=ui.Pixel(self.PADDING))
            ui.Spacer()

    @omni.usd.handle_exception
    async def _deferred_run_batch(self, config):
        if not self._progress_bar:
            self._progress_bar = ProgressPopup(title="Processing")
        self._progress_bar.set_progress(0)
        self._progress_bar.set_cancel_fn(self._batch_cancel)
        self._progress_bar.show()
        error = await LightspeedTextureProcessingCore.lss_async_batch_process_entire_capture_layer(
            config, progress_callback=self._batch_set_progress, context_name=TrexContexts.STAGE_CRAFT.value
        )
        if error:
            self._error_popup = ErrorPopup("An error occurred while processing", error, window_size=(350, 150))
            self._error_popup.show()
        if self._progress_bar:
            self._progress_bar.hide()
            self._progress_bar = None

    def _run_batch(self, async_batch_fn, config):
        if self.__run_batch_task:
            self.__run_batch_task.cancel()
        self.__run_batch_task = asyncio.ensure_future(async_batch_fn(config))

    def _batch_cancel(self):
        if self.__run_batch_task:
            self.__run_batch_task.cancel()
        self.__run_batch_task = None

    def _batch_set_progress(self, progress):
        if not self._progress_bar:
            self._progress_bar = ProgressPopup(title="Processing")
            self._progress_bar.show()
        self._progress_bar.set_progress(progress)

    @property
    def button_name(self) -> str:
        return "Texture"

    @property
    def button_priority(self) -> int:
        return 20
