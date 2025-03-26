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
import uuid
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

import carb
import carb.tokens
import omni.client
import omni.ui as ui
import omni.usd
from omni.flux.lookdev.core import LookDevCore as _LookDevCore
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.kit.viewport.utility import get_active_viewport
from pxr import UsdGeom, UsdShade
from pydantic import Field

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD  # noqa PLE0402


class MassTexturePreview(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        # tmp data
        temp_usd: Optional[str] = Field(None, repr=False)

    name = "MassTexturePreview"
    tooltip = "This plugin is a fake check plugin that we use to show texture preview (in viewport or not)"
    data_type = Data
    display_name = "Mass Texture Preview"

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to check if asset paths on the selected prims in the attributes listed in schema
        data's `conversion_args` are dds encoded

        Note: This is intended to be run on Shader prims.

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the check passed, False if not
        """
        if schema_data.expose_mass_queue_action_ui:
            # save a tmp USD file for mass ingestion preview
            token = carb.tokens.get_tokens_interface()
            temp_dir = token.resolve("${temp}")
            temp_usd = Path(temp_dir).joinpath(f"{str(uuid.uuid4()).replace('-', '')}.usd")
            schema_data.temp_usd = omni.client.normalize_url(str(temp_usd))
            context = omni.usd.get_context(schema_data.context_name)
            await context.save_as_stage_async(schema_data.temp_usd)

        return True, "Pass", None

    @omni.usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to triangulate the mesh prims (including geom subsets)

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the data where fixed, False if not
        """
        return True, "Pass", None

    def _mass_build_queue_action_ui(
        self, schema_data: Data, default_actions: List[Callable[[], Any]], callback: Callable[[str], Any]
    ) -> None:
        """
        Default exposed action for Mass validation. The UI will be built into the delegate of the mass queue.
        For example, you can add a button to open the asset into a USD viewport
        """

        @omni.usd.handle_exception
        async def __deferred_open_output_file():
            viewport_api = get_active_viewport(usd_context_name=schema_data.context_name)
            if viewport_api is not None:
                carb.log_error("Can't open the stage, no viewport")
                return

            # get textures
            if schema_data.temp_usd is not None:
                lookdev_core = _LookDevCore(schema_data.context_name)
                # with omni.kit.undo.group():
                stage = await lookdev_core.create_lookdev_stage()
                # here we want to add the current stage as a layer, and assign materials with texture(s) to the same
                # binding than the default material of the lookdev stage
                omni.kit.commands.execute(
                    "CreateOrInsertSublayer",
                    layer_identifier=stage.GetRootLayer().identifier,
                    sublayer_position=0,
                    new_layer_path=schema_data.temp_usd,
                    transfer_root_content=False,
                    create_or_insert=False,
                    usd_context=schema_data.context_name,
                )
                # get all material from the ingestion layer
                default_material = lookdev_core.get_default_material_path()
                text_material_prims = []
                for prim in stage.TraverseAll():
                    if not prim.IsA(UsdShade.Material):
                        continue
                    stack = prim.GetPrimStack()
                    for prim_spec in stack:
                        if str(_OmniUrl(prim_spec.layer.realPath)) == str(_OmniUrl(schema_data.temp_usd)):
                            text_material_prims.append(prim)
                            break
                if text_material_prims:
                    for prim in stage.TraverseAll():
                        if prim.IsA(UsdGeom.Subset) or prim.IsA(UsdGeom.Mesh):
                            material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
                            if material and str(material.GetPath()) == default_material:
                                omni.kit.commands.execute(
                                    "BindMaterialCommand",
                                    prim_path=str(prim.GetPath()),
                                    # for now we can only handle 1 set of texture
                                    material_path=str(text_material_prims[0].GetPath()),
                                    strength=UsdShade.Tokens.strongerThanDescendants,
                                    stage=stage,
                                )
                callback("show_in_viewport")

        def __open_output_file():
            asyncio.ensure_future(__deferred_open_output_file())

        # for mass, we only have one input.
        with ui.VStack(width=ui.Pixel(28), height=ui.Pixel(28)):
            ui.Spacer(height=ui.Pixel(2))
            with ui.ZStack():
                ui.Rectangle(name="BackgroundWithWhiteBorder")
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(2))
                    ui.Image(
                        "",
                        name="ShowInViewport",
                        tooltip="Show in viewport",
                        mouse_pressed_fn=lambda x, y, b, m: __open_output_file(),
                        width=ui.Pixel(24),
                        height=ui.Pixel(24),
                    )
                    ui.Spacer(width=ui.Pixel(2))
            ui.Spacer(height=ui.Pixel(2))

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")
