"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

import asyncio
import time
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Any, List, Optional, Tuple

import carb
import omni.kit.app
import omni.ui as ui
import omni.usd
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS as _SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.info_icon.widget import InfoIconWidget as _InfoIconWidget
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.validator.factory import InOutDataFlow as _InOutDataFlow
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from omni.flux.validator.factory import utils as _validator_factory_utils
from omni.kit.widget.prompt import Prompt
from pydantic import validator

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD

# Placeholders until the modules are loaded asynchronously
_get_factory_instance, _OversizedBehavior, _RemixClientError, _InferenceStep = None, None, None, None


class InferenceMode(Enum):
    SPEED = "Speed"
    QUALITY = "Quality"


class GeneratePBRMaterial(_CheckBaseUSD):
    _IMPORT_TIMEOUT_SECONDS = 60  # Max recorded loading time for the lib was about 50 seconds
    _DEFAULT_UI_WIDTH_PIXEL = 115

    class Data(_CheckBaseUSD.Data):
        model_artifact_path: Path
        config_artifact_path: Path
        subdirectory_per_input: bool = True
        min_inference_resolution: int = 64
        max_inference_resolution: int = 512
        noise_level: Optional[float] = None
        denoising_steps: Optional[int] = None
        inference_mode: InferenceMode = InferenceMode.QUALITY

        @validator("model_artifact_path", "config_artifact_path", allow_reuse=True)
        def file_exists(cls, v):  # noqa N805
            resolved_path = carb.tokens.get_tokens_interface().resolve(str(v))
            file_url = _OmniUrl(resolved_path)
            if not file_url.exists or not file_url.is_file:
                raise ValueError("The path must point to a valid file.")
            return Path(resolved_path)

        _compatible_data_flow_names = ["InOutData"]
        data_flows: Optional[List[_InOutDataFlow]] = None  # override base argument with the good typing

        class Config(_CheckBaseUSD.Data.Config):
            validate_assignment = True

    name = "GeneratePBRMaterial"
    display_name = "Generate PBR Material"
    tooltip = (
        "This plugin will generate PBR Materials from a single color texture.\n\n"
        "NOTE: Input textures larger than 512x512 can be used but will cause more artifacts in the output textures"
    )
    data_type = Data

    def __init__(self):
        super().__init__()

        # Get the current event loop & run the async __initialize_async function and wait for it to complete
        self._initialized = False
        asyncio.ensure_future(self.__initialize_async())

    @omni.usd.handle_exception
    async def __initialize_async(self):
        with Prompt("AI Tools Loading", "Initializing AI Tools...", modal=True, ok_button_text=None, no_title_bar=True):
            for _ in range(10):
                await omni.kit.app.get_app().next_update_async()

            # Start importing the dependencies
            global _get_factory_instance, _OversizedBehavior, _RemixClientError, _InferenceStep
            from remix.client import get_factory_instance as _get_factory_instance
            from remix.client.common.enums import OversizedBehavior as _OversizedBehavior
            from remix.client.common.exceptions import RemixClientError as _RemixClientError
            from remix.models.i2m.utils import InferenceStep as _InferenceStep

            # Initialize instance variables
            self._OVERSIZE_BEHAVIOR_MAP = {
                InferenceMode.SPEED: _OversizedBehavior.DOWNSCALE,
                InferenceMode.QUALITY: _OversizedBehavior.PATCHWISE,
            }

            self._is_executed = False
            self._inference_mode_changed_sub = None
            self._initialized = True

    @omni.usd.handle_exception
    async def _ensure_initialized(self) -> bool:
        start_time = time.time()
        while not self._initialized:
            if time.time() - start_time > self._IMPORT_TIMEOUT_SECONDS:
                return False
            await omni.kit.app.get_app().next_update_async()
        return True

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to check the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the check passed, False if not
        """
        loaded = await self._ensure_initialized()
        if not loaded:
            return False, "An error occurred while attempting to load the extension dependencies", None

        message = "Check:\n"

        if not selector_plugin_data:
            message += "- SKIP: No selected prims"
            return True, message, None

        # Expect texture selector where we get a list of (attribute_prim_path, asset_file_path)
        if not all(isinstance(data, tuple) and len(data) == 2 for data in selector_plugin_data):
            message += "- FAIL: Textures must be selected for this plugin to work correctly. Use a different selector."
            return False, message, None

        if self._is_executed:
            message += "- SUCCESS: Prims were processed successfully."
        else:
            message += "- FAIL: Prims were not processed."

        return self._is_executed, message, None

    @omni.usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to fix the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the data where fixed, False if not
        """
        loaded = await self._ensure_initialized()
        if not loaded:
            return False, "An error occurred while attempting to load the extension dependencies", None

        message = "Fix:\n"
        data = None
        progress = 0
        success = True
        current_step = None

        self.on_progress(progress, "Start", False)

        if not selector_plugin_data:
            return success, message, data

        # Every texture will go through every inference step + Load the inference model
        progress_delta = 1 / (len(selector_plugin_data) * len(_InferenceStep) + 2)

        progress_message = "LOADING: Loading the AI Model"
        message += f"- {progress_message}\n"
        progress += progress_delta
        self.on_progress(progress, progress_message, success)

        # If using Speed Inference, the memory footprint will be that of the output resolution (4x input)
        # For a 512x512 max size, that means a 2k output all in memory which takes > 24GB VRAM.
        # Doing this will reduce the output down to 1k which takes about 7.5GB VRAM
        max_resolution = (
            schema_data.max_inference_resolution // 2
            if schema_data.inference_mode == InferenceMode.SPEED
            else schema_data.max_inference_resolution
        )

        with _get_factory_instance().get_plugin("local_I2M")(  # noqa PLE1102
            schema_data.model_artifact_path,
            schema_data.config_artifact_path,
            min_resolution=schema_data.min_inference_resolution,
            max_resolution=max_resolution,
            noise_level=schema_data.noise_level,
            denoising_steps=schema_data.denoising_steps,
            oversized_behavior=self._OVERSIZE_BEHAVIOR_MAP[schema_data.inference_mode],
            supported_extensions=_SUPPORTED_TEXTURE_EXTENSIONS,
        ) as model:
            progress_message = "LOADED: Successfully loaded the AI Model"
            message += f"- {progress_message}\n"
            progress += progress_delta
            self.on_progress(progress, progress_message, success)

            def on_inference_progress(step: _InferenceStep, in_progress: bool):
                nonlocal progress
                nonlocal message
                nonlocal success
                nonlocal current_step
                # Whe completing a step, present progress
                if in_progress or current_step == step:
                    return
                step_progress = f"PROCESSING: {step.value}"
                message += f"- {step_progress}\n"
                progress += progress_delta
                current_step = step
                self.on_progress(progress, step_progress, success)

            for _, asset_path in selector_plugin_data:
                asset_url = _OmniUrl(asset_path)
                if not asset_url.exists:
                    success = False
                    progress_message = f"FAIL: The texture asset does not exist ({asset_path})"
                    message += f"- {progress_message}\n"
                    progress += len(_InferenceStep)
                    self.on_progress(progress, progress_message, success)
                    continue

                _validator_factory_utils.push_input_data(schema_data, [asset_path])

                output_directory = (
                    str(_OmniUrl(asset_url.parent_url) / asset_url.stem)
                    if schema_data.subdirectory_per_input
                    else asset_url.parent_url
                )

                try:
                    inference_output = await model.infer_async(
                        [Path(str(asset_url))], output_directory, on_inference_progress
                    )
                except _RemixClientError as e:
                    success = False
                    progress_message = f"FAIL: {e}"
                    message += f"- {progress_message}\n"
                    progress += progress_delta
                    self.on_progress(progress, progress_message, success)
                    continue

                for output_paths in inference_output.values():
                    _validator_factory_utils.push_output_data(schema_data, output_paths)

                progress_message = f"SUCCESS: The PBR material was generated: {str(asset_url)}"
                message += f"- {progress_message}\n"
                self.on_progress(progress, progress_message, success)

        self._is_executed = success
        return success, message, data

    @omni.usd.handle_exception
    async def _mass_build_ui(self, schema_data: Data) -> Any:
        """
        Build the mass UI of a plugin. A mass UI is a UI that will expose some UI for mass processing. Mass processing
        will call multiple validation core. So this UI exposes controllers that will be passed to each schema.

        Args:
            schema_data: the data of the plugin from the schema

        Returns:
            Anything from the implementation
        """
        await self._build_ui(schema_data)

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        with ui.HStack():
            ui.Label("Inference Mode", width=self._DEFAULT_UI_WIDTH_PIXEL, name="PropertiesWidgetLabel")

            ui.Spacer(height=0, width=ui.Pixel(8))

            combobox_options = [i.value for i in InferenceMode]
            inference_mode_combobox = ui.ComboBox(
                combobox_options.index(schema_data.inference_mode.value), *combobox_options
            )

            ui.Spacer(width=ui.Pixel(8))

            with ui.VStack(width=0):
                ui.Spacer(width=0)
                max_res = schema_data.max_inference_resolution
                _InfoIconWidget(
                    f"Select the AI Model inference mode.\n\n"  # noqa E501
                    f"- {InferenceMode.SPEED.value}:\n"  # noqa E501
                    f"    Will downscale the input image to a resolution of {max_res // 2}x{max_res // 2} and output images of size {max_res * 2}x{max_res * 2}.\n"  # noqa E501
                    f"    This is quicker but limits the output images' resolutions. It also uses more VRAM since the entire output is in memory.\n"  # noqa E501
                    f"- {InferenceMode.QUALITY.value}:\n"  # noqa E501
                    f"    Will run many inferences of size {max_res}x{max_res} within the input image, until the complete output images are\n"  # noqa E501
                    f"    generated. The inference process will be slower and memory usage will increase exponentially in relation\n"  # noqa E501
                    f"    to the input image resolution but the output images will also be higher resolution (4x the input resolution).\n\n"  # noqa E501
                    f"NOTE:\n"  # noqa E501
                    f'    When running in "{InferenceMode.QUALITY.value}" mode, inputting images larger than {max_res * 2}x{max_res * 2} may result in visual artifacts being\n'  # noqa E501
                    f"    introduced to the generated maps."  # noqa E501
                )
                ui.Spacer(width=0)

        self._inference_mode_changed_sub = inference_mode_combobox.model.subscribe_item_changed_fn(
            partial(self.__update_inference_mode, schema_data)
        )

    def __update_inference_mode(self, schema_data: Data, model, _):
        try:
            schema_data.inference_mode = list(InferenceMode)[model.get_item_value_model().as_int]
        except ValueError as e:
            carb.log_error(f"Unable to update inference mode: {e}")
            model.get_item_value_model().set_value(list(InferenceMode).index(schema_data.inference_mode))

    def destroy(self):
        self._inference_mode_changed_sub = None

        super().destroy()
