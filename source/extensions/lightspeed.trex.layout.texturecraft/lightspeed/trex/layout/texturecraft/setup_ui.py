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
from lightspeed.upscale.core import UpscalerCore
from omni.flux.utils.widget.background_pattern import create_widget_with_pattern as _create_widget_with_pattern


class UpscaleProcessConfig(Enum):
    DEFAULT = (
        UpscalerCore.perform_upscale,
        constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
        constants.MATERIAL_INPUTS_DIFFUSE_TEXTURE,
        "_upscaled4x.png",
    )
    OVERWRITE = (
        functools.partial(UpscalerCore.perform_upscale, overwrite=True),
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
    def __init__(self, ext_id):
        super().__init__(ext_id)
        self.__run_batch_task = None

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
                ui.Spacer()
                with ui.ZStack(height=ui.Pixel(0), width=ui.Percent(28)):
                    ui.Rectangle(name="WorkspaceBackground")
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8))
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))
                            ui.Label("Upscale", name="Title1", alignment=ui.Alignment.CENTER, height=0)
                            with ui.VStack():
                                ui.Label("Batch Upscale all textures from current capture layer", height=ui.Pixel(50))
                                _create_widget_with_pattern(
                                    functools.partial(
                                        ui.Button,
                                        "Skip already converted one",
                                        name="NoBackground",
                                        clicked_fn=functools.partial(
                                            self._run_batch,
                                            self._deferred_run_batch,
                                            UpscaleProcessConfig.DEFAULT.value,
                                        ),
                                    ),
                                    "BackgroundButton",
                                    height=ui.Pixel(24),
                                    background_margin=(2, 2),
                                )

                                _create_widget_with_pattern(
                                    functools.partial(
                                        ui.Button,
                                        "Overwrite all textures (re-convert everything)",
                                        name="NoBackground",
                                        clicked_fn=functools.partial(
                                            self._run_batch,
                                            self._deferred_run_batch,
                                            UpscaleProcessConfig.OVERWRITE.value,
                                        ),
                                    ),
                                    "BackgroundButton",
                                    height=ui.Pixel(24),
                                    background_margin=(2, 2),
                                )

                            ui.Spacer(height=ui.Pixel(8))
                        ui.Spacer(width=ui.Pixel(8))
                ui.Spacer()
                with ui.ZStack(height=ui.Pixel(0), width=ui.Percent(28)):
                    ui.Rectangle(name="WorkspaceBackground")
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8))
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))
                            ui.Label("Color to normal", alignment=ui.Alignment.CENTER, name="Title1", height=0)
                            with ui.VStack():
                                ui.Label(
                                    "Batch Convert all textures from current capture layer to Normal Maps",
                                    height=ui.Pixel(50),
                                )

                                _create_widget_with_pattern(
                                    functools.partial(
                                        ui.Button,
                                        "Skip already converted one",
                                        name="NoBackground",
                                        clicked_fn=functools.partial(
                                            self._run_batch,
                                            self._deferred_run_batch,
                                            ColorToNormalProcessConfig.DEFAULT.value,
                                        ),
                                    ),
                                    "BackgroundButton",
                                    height=ui.Pixel(24),
                                    background_margin=(2, 2),
                                )

                                _create_widget_with_pattern(
                                    functools.partial(
                                        ui.Button,
                                        "Overwrite all textures (re-convert everything)",
                                        name="NoBackground",
                                        clicked_fn=functools.partial(
                                            self._run_batch,
                                            self._deferred_run_batch,
                                            ColorToNormalProcessConfig.OVERWRITE.value,
                                        ),
                                    ),
                                    "BackgroundButton",
                                    height=ui.Pixel(24),
                                    background_margin=(2, 2),
                                )

                            ui.Spacer(height=ui.Pixel(8))
                        ui.Spacer(width=ui.Pixel(8))
                ui.Spacer()
                with ui.ZStack(height=ui.Pixel(0), width=ui.Percent(28)):
                    ui.Rectangle(name="WorkspaceBackground")
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8))
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))
                            ui.Label("Color to roughness", alignment=ui.Alignment.CENTER, name="Title1", height=0)
                            with ui.VStack():
                                ui.Label(
                                    "Batch Convert all textures from current capture layer to Roughness Maps",
                                    height=ui.Pixel(50),
                                )
                                _create_widget_with_pattern(
                                    functools.partial(
                                        ui.Button,
                                        "Skip already converted one",
                                        name="NoBackground",
                                        clicked_fn=functools.partial(
                                            self._run_batch,
                                            self._deferred_run_batch,
                                            ColorToRoughnessProcessConfig.DEFAULT.value,
                                        ),
                                    ),
                                    "BackgroundButton",
                                    height=ui.Pixel(24),
                                    background_margin=(2, 2),
                                )

                                _create_widget_with_pattern(
                                    functools.partial(
                                        ui.Button,
                                        "Overwrite all textures (re-convert everything)",
                                        name="NoBackground",
                                        clicked_fn=functools.partial(
                                            self._run_batch,
                                            self._deferred_run_batch,
                                            ColorToRoughnessProcessConfig.OVERWRITE.value,
                                        ),
                                    ),
                                    "BackgroundButton",
                                    height=ui.Pixel(24),
                                    background_margin=(2, 2),
                                )
                            ui.Spacer(height=ui.Pixel(8))
                        ui.Spacer(width=ui.Pixel(8))
                ui.Spacer()
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
            self._error_popup = ErrorPopup("An error occurred while processing", error, "", window_size=(350, 150))
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
        return "TextureCraft"

    @property
    def button_priority(self) -> int:
        return 20
