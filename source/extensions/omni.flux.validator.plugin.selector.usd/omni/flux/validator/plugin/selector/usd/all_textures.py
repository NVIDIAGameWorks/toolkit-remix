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

from typing import Any, List, Tuple

import omni.ui as ui
import omni.usd
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.utils.common.path_utils import get_invalid_extensions as _get_invalid_extensions
from omni.flux.validator.factory import SelectorBase as _SelectorBase
from pxr import Sdf, UsdShade


class AllTextures(_SelectorBase):
    class Data(_SelectorBase.Data):
        filtered_input_names: List[str] = None

    name = "AllTextures"
    tooltip = "This plugin will select all textures in the stage"
    data_type = Data

    @omni.usd.handle_exception
    async def _select(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to select the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the previous selector plugin

        Returns: True if ok + message + the selected data
        """
        stage = omni.usd.get_context(context_plugin_data).get_stage()
        all_shaders = [prim_ref for prim_ref in stage.TraverseAll() if prim_ref.IsA(UsdShade.Shader)]
        all_textures = []

        for shader_prim in all_shaders:
            shader = UsdShade.Shader(shader_prim)
            for shader_input in shader.GetInputs():
                # Make sure the input matches the filter if set
                if (
                    schema_data.filtered_input_names
                    and shader_input.GetBaseName() not in schema_data.filtered_input_names
                ):
                    continue
                # Make sure the input expects an asset
                if shader_input.GetTypeName() != Sdf.ValueTypeNames.Asset:
                    continue
                # Make sure the asset is a supported texture
                texture_asset_path = shader_input.Get().resolvedPath
                if _get_invalid_extensions(
                    file_paths=[texture_asset_path], valid_extensions=SUPPORTED_TEXTURE_EXTENSIONS
                ):
                    continue
                # Build the full property path
                texture_input_path = shader_prim.GetPath().AppendProperty(shader_input.GetFullName())
                # Store the texture property and the asset path
                all_textures.append((str(texture_input_path), str(texture_asset_path)))

        return True, "Ok", all_textures

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")
