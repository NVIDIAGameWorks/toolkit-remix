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

__all__ = ["TextureReplacementsCore"]

from contextlib import nullcontext
from pathlib import Path

import omni.usd
from lightspeed.trex.utils.common.asset_utils import TEXTURE_TYPE_INPUT_MAP as _TEXTURE_TYPE_INPUT_MAP
from lightspeed.trex.utils.common.asset_utils import get_ingested_texture_type as _get_ingested_texture_type
from lightspeed.trex.utils.common.asset_utils import get_texture_type_input_name as _get_texture_type_input_name
from lightspeed.trex.utils.common.prim_utils import PrimTypes as _PrimTypes
from lightspeed.trex.utils.common.prim_utils import filter_prims_paths as _filter_prims_paths
from lightspeed.trex.utils.common.prim_utils import get_extended_selection as _get_extended_selection
from lightspeed.trex.utils.common.prim_utils import get_prim_paths as _get_prim_paths
from lightspeed.trex.utils.common.prim_utils import includes_hash as _includes_hash
from lightspeed.trex.utils.common.prim_utils import is_shader_prototype as _is_shader_prototype
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS as _SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.asset_importer.core.data_models import TextureTypeNames as _TextureTypeNames
from omni.flux.asset_importer.core.data_models import TextureTypes as _TextureTypes
from omni.flux.material_api import ShaderInfoAPI as _ShaderInfoAPI
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl
from omni.kit import commands, undo
from pxr import Sdf, UsdShade

from .data_models import (
    GetTexturesQueryModel,
    PrimsResponseModel,
    ReplaceTexturesRequestModel,
    TextureMaterialPathParamModel,
    TextureReplacementsValidators,
    TexturesResponseModel,
)


class TextureReplacementsCore:
    def __init__(self, context_name: str = ""):
        self._default_attr = {
            "_context_name": None,
            "_context": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)

    # DATA MODEL FUNCTIONS

    def get_texture_prims_assets_with_data_models(self, query: GetTexturesQueryModel) -> TexturesResponseModel:
        return TexturesResponseModel(
            textures=self.get_texture_prims_assets(
                asset_hashes=query.asset_hashes,
                texture_types=query.texture_types,
                return_selection=query.return_selection,
                filter_session_prims=query.filter_session_prims,
                layer_id=query.layer_identifier,
                exists=query.exists,
            )
        )

    def replace_texture_with_data_models(self, body: ReplaceTexturesRequestModel):
        self.replace_textures(body.textures)

    def get_texture_material_with_data_models(self, params: TextureMaterialPathParamModel) -> PrimsResponseModel:
        material_asset_path = self.get_texture_material(params.texture_asset_path)
        if material_asset_path is None:
            raise ValueError("Unable to find a material associated to the given texture")
        return PrimsResponseModel(asset_paths=[material_asset_path])

    async def get_texture_material_inputs_with_data_models(
        self, params: TextureMaterialPathParamModel
    ) -> PrimsResponseModel:
        material_inputs = await self.get_expected_texture_material_inputs(params.texture_asset_path)
        if material_inputs is None:
            raise ValueError("Unable to find a material associated to the given texture")
        return PrimsResponseModel(asset_paths=material_inputs)

    async def get_texture_expected_material_inputs_with_data_models(
        self,
        material_params: TextureMaterialPathParamModel,
        texture_type: _TextureTypeNames | str | None = None,
    ) -> PrimsResponseModel:
        material_inputs = await self.get_expected_texture_material_inputs(
            material_params.texture_asset_path,
            texture_type=_TextureTypes[texture_type.value],
        )
        if material_inputs is None:
            raise ValueError("Unable to find a material associated to the given texture")
        return PrimsResponseModel(asset_paths=material_inputs)

    # TRADITIONAL FUNCTIONS

    def get_texture_prims_assets(
        self,
        asset_hashes: set[str] | None,
        texture_types: set[_TextureTypeNames] | None,
        return_selection: bool = False,
        filter_session_prims: bool = True,
        layer_id: str | None = None,
        exists: bool = True,
    ) -> list[tuple[str, str]]:
        """
        Get the list of (texture property, asset path) filtered by shader input name for the entire stage or the
        current selection

        Args:
            asset_hashes: A set of asset hashes to keep when filtering material asset paths
            texture_types: A set of texture types to keep when filtering textures
            return_selection: Whether to return the current selection or all prims in the stage
            filter_session_prims: Whether to filter prims defined on the session prim or not
            layer_id: Look for assets that exists or not on a given layer. Use the `exists` query parameter to set
                      whether existing or non-existing prims should be returned.
            exists: Filter an asset if it exists or not on a given layer. Use in conjunction with `layer_identifier` to
                    filter on a given layer, otherwise this parameter will be ignored.

        Returns:
            A list of tuples in the format (texture property, asset path) where the texture property will always be
            a shader input and the asset path will be the absolute path to the texture asset
        """
        stage = self._context.get_stage()
        textures = []

        selection = None
        if return_selection:
            selection = _get_extended_selection(self._context_name)

        # Get every asset-type input for every shader and validate that the asset path has a supported texture extension
        for shader_path in _filter_prims_paths(
            lambda prim: bool(_is_shader_prototype(prim) and _includes_hash(prim, asset_hashes)),
            prim_paths=selection,
            filter_session_prims=filter_session_prims,
            layer_id=layer_id,
            exists=exists,
            context_name=self._context_name,
        ):
            shader = UsdShade.Shader(stage.GetPrimAtPath(shader_path))
            for shader_input in shader.GetInputs():
                # Make sure the input matches the filter if set
                if texture_types is not None:
                    texture_type_names = [
                        _get_texture_type_input_name(_TextureTypes[texture_type.value])
                        for texture_type in texture_types
                    ]
                    if shader_input.GetFullName() not in texture_type_names:
                        continue
                # Make sure the input expects an asset
                if shader_input.GetTypeName() != Sdf.ValueTypeNames.Asset:
                    continue
                # Make sure the asset is a supported texture
                texture_asset_path = shader_input.Get().resolvedPath
                if OmniUrl(texture_asset_path).suffix.lower() not in _SUPPORTED_TEXTURE_EXTENSIONS:
                    continue
                # Build the full property path
                texture_input_path = Sdf.Path(shader_path).AppendProperty(shader_input.GetFullName())
                # Store the texture property and the asset path
                textures.append((str(texture_input_path), str(texture_asset_path)))

        return textures

    def replace_textures(
        self, textures: list[tuple[str, str | Path | None]], force: bool = False, use_undo_group: bool = True
    ):
        """
        Replace a list of textures

        Args:
            textures: A list of tuples in the format (texture property, asset path) where the texture property should be
                      a shader input and the asset path should be the absolute path to the texture asset
            force: Whether to force replace the texture or validate it was ingested correctly
            use_undo_group: Whether to use an undo group for the texture replacements
        """
        with undo.group() if use_undo_group else nullcontext():
            for texture_attr_path, texture_asset_path in textures:
                try:
                    TextureReplacementsValidators.is_valid_texture_prim(
                        (texture_attr_path, texture_asset_path), self._context_name
                    )
                    TextureReplacementsValidators.is_valid_texture_asset((texture_attr_path, texture_asset_path), force)
                except ValueError:
                    continue

                attr_type = None
                attr_path = Sdf.Path(texture_attr_path)
                prim = self._context.get_stage().GetPrimAtPath(attr_path.GetPrimPath())
                for input_property in _ShaderInfoAPI(prim).get_input_properties():
                    if attr_path.name == input_property.GetName():
                        attr_type = Sdf.ValueTypeNames.Find(input_property.GetTypeName())
                        break

                if texture_asset_path:
                    commands.execute(
                        "ChangeProperty",
                        prop_path=texture_attr_path,
                        value=Sdf.AssetPath(
                            omni.usd.make_path_relative_to_current_edit_target(
                                str(texture_asset_path), stage=self._context.get_stage()
                            )
                        ),
                        prev=None,
                        type_to_create_if_not_exist=attr_type,
                        usd_context_name=self._context_name,
                        target_layer=self._context.get_stage().GetEditTarget().GetLayer(),
                    )
                else:
                    commands.execute(
                        "RemoveProperty",
                        prop_path=texture_attr_path,
                        usd_context_name=self._context_name,
                    )

    def get_texture_material(self, texture_prim_path: str) -> str | None:
        """
        Get a material prim path from a texture prim attribute's path

        Args:
            texture_prim_path: The prim path to a shader input attribute

        Returns:
            the prim path to the associated material or None if no material is found
        """
        stage = self._context.get_stage()

        # Get the prim path for the shader input
        shader_path = Sdf.Path(texture_prim_path).GetPrimPath()
        # Get all materials in the stage. Materials are linked to their shader via their output
        material_paths = _get_prim_paths(prim_type=_PrimTypes.MATERIALS)

        for material_path in material_paths:
            # Get the outputs for the material
            for output in UsdShade.Material(stage.GetPrimAtPath(material_path)).GetOutputs():
                # Get the connection of the output
                for connection_path in output.GetRawConnectedSourcePaths():
                    # Make sure the output connection points to our shader
                    if Sdf.Path(connection_path).GetPrimPath() == shader_path:
                        return material_path

        # No material is connected to our shader
        return None

    async def get_expected_texture_material_inputs(
        self,
        texture_prim_path: str,
        texture_type: _TextureTypes | str | None = None,
    ) -> list[str]:
        stage = self._context.get_stage()

        shader_path = Sdf.Path(texture_prim_path).GetPrimPath()
        shader_prim = stage.GetPrimAtPath(shader_path)

        # If no file path is provided, get all the valid inputs
        if texture_type is None:
            filter_input_names = _TEXTURE_TYPE_INPUT_MAP.values()
        # If forced_texture_type is set, get the input for forced_texture_type
        elif isinstance(texture_type, _TextureTypes):
            filter_input_names = [_get_texture_type_input_name(texture_type)]
        # Otherwise, get the input for the texture type inferred from the texture name
        else:
            texture_type = _get_ingested_texture_type(texture_type)
            filter_input_names = [_get_texture_type_input_name(texture_type)]

        inputs = set()
        for input_property in _ShaderInfoAPI(shader_prim).get_input_properties():
            if input_property.GetName() in filter_input_names:
                inputs.add(str(shader_path.AppendProperty(input_property.GetName())))

        return list(inputs)

    def destroy(self):
        _reset_default_attrs(self)
