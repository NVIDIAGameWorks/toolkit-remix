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

__all__ = ["TextureReplacementsValidators"]

from pathlib import Path

import omni.usd
from lightspeed.trex.utils.common.asset_utils import is_asset_ingested
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.material_api import ShaderInfoAPI
from omni.flux.utils.common.omni_url import OmniUrl
from pxr import Sdf, UsdShade


class TextureReplacementsValidators:
    @classmethod
    def is_valid_texture_prim(cls, texture_tuple: tuple[str, Path], context_name: str):
        property_path, _ = texture_tuple

        try:
            path = Sdf.Path(property_path)
            if not path:
                raise ValueError("Invalid prim path")
        except Exception as e:
            raise ValueError(f"The string is not a valid path: {property_path}") from e

        prim_path = path.GetPrimPath()
        prim = omni.usd.get_context(context_name).get_stage().GetPrimAtPath(prim_path)
        if not prim:
            raise ValueError(f"The prim path does not exist in the current stage: {prim_path}")

        if not prim.IsA(UsdShade.Shader):
            raise ValueError(f"The property path does not point to a valid USD shader property: {property_path}")

        for input_property in ShaderInfoAPI(prim).get_input_properties():
            if input_property.GetName() == path.name:
                return texture_tuple

        raise ValueError(f"The property path does not point to a valid USD shader input: {property_path}")

    @classmethod
    def is_valid_texture_asset(cls, texture_tuple: tuple[str, Path], force: bool):
        _, asset_path = texture_tuple

        if asset_path is None:
            return texture_tuple

        asset_url = OmniUrl(asset_path)

        if asset_url.suffix.lower() not in SUPPORTED_TEXTURE_EXTENSIONS:
            raise ValueError(f"The asset path points to an unsupported texture file type: {asset_path}")

        if not asset_url.exists:
            raise ValueError(f"The asset path does not point to an existing file: {asset_path}")

        if not is_asset_ingested(str(asset_url)) and not force:
            raise ValueError(f"The asset was not ingested. Ingest the asset before replacing the texture: {asset_path}")

        return texture_tuple

    @classmethod
    def layer_is_in_project(cls, layer_id: Path | None, context_name: str):
        if layer_id is None:
            return layer_id

        layer = Sdf.Layer.FindOrOpen(str(layer_id))
        if not layer:
            raise ValueError(f"The layer does not exist: {layer_id}")

        stage = omni.usd.get_context(context_name).get_stage()
        project_layer_ids = [
            _layer.identifier for _layer in stage.GetLayerStack(includeSessionLayers=False)
        ] + stage.GetMutedLayers()

        # Make sure the layer is in the currently opened project
        if layer.identifier not in project_layer_ids:
            raise ValueError(f"The layer is not present in the loaded project's layer stack: {layer_id}")

        return layer_id
