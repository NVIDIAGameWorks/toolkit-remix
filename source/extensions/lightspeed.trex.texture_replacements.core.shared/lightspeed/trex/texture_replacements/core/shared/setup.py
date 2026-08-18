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

from pathlib import Path

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
from omni.client.utils import make_relative_url_if_possible as _make_relative_url_if_possible
from omni.kit import commands
from omni.usd import get_context
from pxr import Sdf, UsdShade

from .data_models import (
    GetTexturesQueryModel,
    PrimPathsResponseModel,
    ReplaceTexturesRequestModel,
    TextureMaterialPathParamModel,
    TextureReplacementsValidators,
    TexturesResponseModel,
)
from .data_models.models import TextureReplacement
from .data_models.validators import InvalidTextureInputError
from .commands import REPLACE_TEXTURES_COMMAND


class TextureReplacementsCore:
    """Query and author texture replacements in one USD context."""

    def __init__(self, context_name: str = ""):
        """Initialize texture replacement operations for one USD context.

        Args:
            context_name: Name of the USD context, or an empty string for the default context.
        """
        self._default_attr = {
            "_context_name": None,
            "_context": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._context = get_context(context_name)

    # DATA MODEL FUNCTIONS

    def get_texture_prims_assets_with_data_models(self, query: GetTexturesQueryModel) -> TexturesResponseModel:
        return TexturesResponseModel(
            textures=self.get_texture_prims_assets(
                prim_hashes=query.prim_hashes,
                texture_types=query.texture_types,
                return_selection=query.return_selection,
                filter_session_prims=query.filter_session_prims,
                layer_id=query.layer_identifier,
                exists=query.exists,
            )
        )

    def replace_texture_with_data_models(self, body: ReplaceTexturesRequestModel) -> None:
        """Apply replacements from a validated service request.

        Args:
            body: Request containing the texture property and asset path pairs to apply.

        Raises:
            ValueError: If any texture property or asset path fails validation.
        """
        self.replace_textures(
            body.textures,
            force=body.force,
            expected_current_textures=body.expected_current_textures,
        )

    def get_texture_material_with_data_models(self, params: TextureMaterialPathParamModel) -> PrimPathsResponseModel:
        material_prim_path = self.get_texture_material(params.texture_prim_path)
        if material_prim_path is None:
            raise ValueError("Unable to find a material associated to the given texture")
        return PrimPathsResponseModel(prim_paths=[material_prim_path])

    async def get_texture_material_inputs_with_data_models(
        self, params: TextureMaterialPathParamModel
    ) -> PrimPathsResponseModel:
        material_inputs = await self.get_expected_texture_material_inputs(params.texture_prim_path)
        if material_inputs is None:
            raise ValueError("Unable to find a material associated to the given texture")
        return PrimPathsResponseModel(prim_paths=material_inputs)

    async def get_texture_expected_material_inputs_with_data_models(
        self,
        material_params: TextureMaterialPathParamModel,
        texture_type: _TextureTypeNames | str | None = None,
    ) -> PrimPathsResponseModel:
        material_inputs = await self.get_expected_texture_material_inputs(
            material_params.texture_prim_path,
            texture_type=_TextureTypes[
                texture_type.value if isinstance(texture_type, _TextureTypeNames) else str(texture_type)
            ],
        )
        if material_inputs is None:
            raise ValueError("Unable to find a material associated to the given texture")
        return PrimPathsResponseModel(prim_paths=material_inputs)

    # TRADITIONAL FUNCTIONS

    def get_texture_prims_assets(
        self,
        prim_hashes: set[str] | None,
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
            prim_hashes: A set of prim hashes to keep when filtering material asset paths
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
            lambda prim: bool(_is_shader_prototype(prim) and _includes_hash(prim, prim_hashes)),
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
        self,
        textures: list[tuple[str, str | Path | None]],
        force: bool = False,
        target_layer: Sdf.Layer | None = None,
        expected_current_textures: list[tuple[str, str | Path | None]] | None = None,
    ) -> None:
        """Validate and author a batch of texture replacements.

        The complete batch is validated and its input types are resolved before any authoring command executes.

        Args:
            textures: Shader input property paths paired with replacement asset paths, or None to remove a property.
            force: Whether to bypass source availability and ingestion checks after confirming current authored values.
            target_layer: Layer to author edits on, or None to use the current edit target layer.
            expected_current_textures: Exact target-layer values that authorize a forced replacement.

        Raises:
            ValueError: If the batch, force confirmation, property, or asset path is invalid.
        """
        texture_paths = [texture_path for texture_path, _ in textures]
        if len(texture_paths) != len(set(texture_paths)):
            raise ValueError("Texture replacement target paths must be unique")
        if force and expected_current_textures is None:
            raise ValueError("Forced texture replacement requires expected current values")
        if not force and expected_current_textures is not None:
            raise ValueError("Expected current values are only valid for forced texture replacement")

        expected_paths = (
            [texture_path for texture_path, _ in expected_current_textures]
            if expected_current_textures is not None
            else []
        )
        if len(expected_paths) != len(set(expected_paths)):
            raise ValueError("Expected texture target paths must be unique")
        if expected_current_textures is not None and set(expected_paths) != set(texture_paths):
            raise ValueError("Expected texture target paths must match the replacement batch")

        if not textures:
            return

        stage = self._context.get_stage()
        if stage is None:
            raise RuntimeError(f"No USD stage is open for context '{self._context_name}'")
        texture_input_types = TextureReplacementsValidators.get_texture_input_types(
            texture_paths,
            self._context_name,
            stage=stage,
        )
        for texture_batch, allow_unavailable in (
            (textures, force),
            (expected_current_textures or [], True),
        ):
            for texture in texture_batch:
                TextureReplacementsValidators.is_valid_texture_asset(texture, allow_unavailable)

        edit_layer = target_layer or stage.GetEditTarget().GetLayer()
        prepared_batches = []
        for texture_batch, normalize_paths in (
            (textures, True),
            (expected_current_textures or [], False),
        ):
            replacements = []
            for texture_attr_path, texture_asset_path in texture_batch:
                if texture_asset_path:
                    attr_type = texture_input_types[texture_attr_path]
                    relative_texture_path = str(texture_asset_path)
                    if normalize_paths and not edit_layer.anonymous:
                        relative_texture_path = (
                            _make_relative_url_if_possible(edit_layer.realPath, relative_texture_path)
                            or relative_texture_path
                        )
                    replacements.append(
                        TextureReplacement(Sdf.Path(texture_attr_path), relative_texture_path, attr_type)
                    )
                    continue
                replacements.append(TextureReplacement(Sdf.Path(texture_attr_path), None, None))
            prepared_batches.append(replacements)
        replacements, expected_replacements = prepared_batches

        def verify_expected_replacements() -> None:
            for expected in expected_replacements:
                property_path = expected.property_path
                attribute_spec = edit_layer.GetAttributeAtPath(property_path)
                expected_value = expected.value
                if expected_value is not None and expected.value_type == Sdf.ValueTypeNames.Asset:
                    actual_value = attribute_spec.default if attribute_spec is not None else None
                    actual_url = actual_value.path if isinstance(actual_value, Sdf.AssetPath) else None
                    if edit_layer.anonymous:
                        expected_url = expected_value
                    else:
                        expected_url = Sdf.ComputeAssetPathRelativeToLayer(edit_layer, expected_value)
                        actual_url = (
                            Sdf.ComputeAssetPathRelativeToLayer(edit_layer, actual_url)
                            if actual_url is not None
                            else None
                        )
                    matches = actual_url == expected_url
                    if matches:
                        expected.value = actual_value.path
                    if not matches:
                        raise ValueError(f"Texture target differs from its expected current value: {property_path}")
                    continue
                if expected_value is None:
                    matches = attribute_spec is None
                else:
                    matches = attribute_spec is not None and attribute_spec.default == expected_value
                if not matches:
                    raise ValueError(f"Texture target differs from its expected current value: {property_path}")

        verify_expected_replacements()

        success, _ = commands.execute(
            REPLACE_TEXTURES_COMMAND,
            replacements=replacements,
            target_layer_identifier=edit_layer.identifier,
            expected_replacements=expected_replacements if force else None,
        )
        if not success:
            verify_expected_replacements()
            raise RuntimeError("The texture replacement batch failed")

    def get_valid_texture_inputs(self, texture_input_paths: list[str]) -> list[str]:
        """Filter texture input paths through the canonical shader-input validator.

        Args:
            texture_input_paths: Candidate shader input property paths.

        Returns:
            Accepted paths in their original order.
        """
        valid_inputs = []
        for texture_input_path in texture_input_paths:
            try:
                TextureReplacementsValidators.is_valid_texture_prim(
                    (texture_input_path, None),
                    self._context_name,
                )
            except InvalidTextureInputError:
                continue
            valid_inputs.append(texture_input_path)
        return valid_inputs

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
