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

from pathlib import Path
from typing import Any
from collections.abc import Awaitable, Callable

import omni.client
import omni.kit.app
import omni.ui as ui
import omni.usd
from omni.flux.validator.factory import InOutDataFlow as _InOutDataFlow
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from omni.flux.validator.factory import utils as _validator_factory_utils
from pxr import UsdUtils

from .base.context_base_usd import ContextBaseUSD as _ContextBaseUSD


class DependencyIterator(_ContextBaseUSD):
    class Data(_ContextBaseUSD.Data):
        save_all_layers_on_exit: bool = False
        close_stage_on_exit: bool = False
        # will close each dependency layer at the end. But NOT the main layer. Use close_stage_on_exit for the main
        # layer
        close_dependency_between_round: bool = True

        _compatible_data_flow_names = ["InOutData"]
        data_flows: list[_InOutDataFlow] | None = None  # override base argument with the good typing

    name = "DependencyIterator"
    display_name = "Dependency Iterator"
    tooltip = "This plugin will iterate and open all dependencies (sublayers, references, etc etc)"
    data_type = Data

    @omni.usd.handle_exception
    async def _check(self, schema_data: Data, parent_context: _SetupDataTypeVar) -> tuple[bool, str]:
        """
        Function that will be called to execute the data.

        Args:
            schema_data: the USD file path to check
            parent_context: context data from the parent context

        Returns: True if the check passed, False if not
        """
        context = await self._set_current_context(schema_data, parent_context)
        if not context:
            return False, f"The context {schema_data.computed_context} doesn't exist!"
        return bool(context.get_stage()), str(omni.client.normalize_url(context.get_stage_url()))

    async def _setup(
        self,
        schema_data: Data,
        run_callback: Callable[[_SetupDataTypeVar], Awaitable[None]],
        parent_context: _SetupDataTypeVar,
    ) -> tuple[bool, str, _SetupDataTypeVar]:
        """
        Function that will be executed to set the data. Here we will open the file path and give the stage

        Args:
            schema_data: the data that we should set. Same data than check()
            run_callback: the validation that will be run in the context of this setup
            parent_context: context data from the parent context

        Returns: True if ok + message + data that need to be passed into another plugin
        """
        progress = 0
        self.on_progress(progress, "Start", True)
        context = await self._set_current_context(schema_data, parent_context)
        if not context:
            return False, f"The context {schema_data.computed_context} doesn't exist!", None
        stage = context.get_stage()

        root_layer = stage.GetRootLayer()
        root_layer_identifier = root_layer.identifier
        (all_layers, _assets, _unresolved) = UsdUtils.ComputeAllDependencies(root_layer_identifier)

        if not all_layers:
            all_layers = [layer for layer in stage.GetLayerStack() if not layer.anonymous]
        if all_layers:
            size_layers = len(all_layers)
            to_add = 1 / size_layers
            for i, layer in enumerate(reversed(all_layers)):
                file_path = layer.realPath

                _validator_factory_utils.push_input_data(schema_data, [str(file_path)])

                result, error = await context.open_stage_async(file_path)
                if not result:
                    return False, f"Can't open the file {file_path: {error}}", None
                progress += to_add / 2
                self.on_progress(progress, f"Opened {Path(file_path).name}", True)
                await run_callback(schema_data.computed_context)
                if schema_data.save_all_layers_on_exit:
                    result, error, _saved_layers = await context.save_stage_async()
                    if not result:
                        return False, f"Can't save the file {file_path: {error}}", None

                    _validator_factory_utils.push_output_data(schema_data, [str(file_path)])

                if schema_data.close_dependency_between_round and i != size_layers - 1:
                    await self._close_stage(schema_data.computed_context)

                progress += to_add / 2
                self.on_progress(progress, f"Processed {Path(file_path).name}", True)
        return (
            True,
            f"{len(all_layers)} dependencies processed for: {omni.client.normalize_url(context.get_stage_url())}",
            stage,
        )

    async def _on_exit(self, schema_data: Data, parent_context: _SetupDataTypeVar) -> tuple[bool, str]:
        """
        Function that will be called to after the check of the data. For example, save the input USD stage

        Args:
            schema_data: the data that should be checked
            parent_context: context data from the parent context

        Returns:
            bool: True if the on exit passed, False if not.
            str: the message you want to show, like "Succeeded to exit this context"
        """
        if schema_data.close_stage_on_exit:
            await self._close_stage(schema_data.computed_context)
        return True, "Exit ok"

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        with ui.VStack():
            # context
            with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                with ui.HStack(width=ui.Percent(40)):
                    ui.Spacer()
                    ui.Label("Context", name="PropertiesWidgetLabel")
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(4))
                    _context_field = ui.StringField(
                        height=ui.Pixel(18), style_type_name_override="Field", read_only=True
                    )
                    _context_field.model.set_value(
                        schema_data.context_name
                        if schema_data.context_name is not None
                        else (schema_data.computed_context or "None")
                    )
