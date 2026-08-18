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

__all__ = ["InvalidTextureInputError", "TextureReplacementsValidators"]

from pathlib import Path

import omni.usd
from lightspeed.trex.utils.common.asset_utils import is_asset_ingested
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.material_api import ShaderInfoAPI, UsdShadePropertyPlaceholder
from omni.flux.utils.common.omni_url import OmniUrl
from pxr import Sdf, Tf, Usd, UsdShade

from ..constants import VALID_TEXTURE_INPUT_TYPE_NAMES


class InvalidTextureInputError(ValueError):
    """Identify a candidate that is not a supported USD texture input."""


class TextureReplacementsValidators:
    """Validate texture replacement paths against the active USD context."""

    @classmethod
    def get_texture_input_type(
        cls,
        property_path: str,
        context_name: str,
        *,
        stage: Usd.Stage | None = None,
    ) -> Sdf.ValueTypeName:
        """Resolve the USD type of an Asset or String shader input.

        Authored USD attributes are authoritative. Shader metadata is consulted only when the input has not yet been
        authored on the stage.

        Args:
            property_path: Shader input property path to resolve.
            context_name: USD context containing the shader.
            stage: Already resolved stage, or None to resolve it from ``context_name``.

        Returns:
            The input's Asset or String USD value type.

        Raises:
            InvalidTextureInputError: If the path, shader, or texture input is invalid.
            RuntimeError: If the stage or shader registry is unavailable.
        """
        resolved_stage = stage or omni.usd.get_context(context_name).get_stage()
        if resolved_stage is None:
            raise RuntimeError(f"No USD stage is open for context '{context_name}'")
        return cls._get_texture_input_type(property_path, resolved_stage, {})

    @classmethod
    def get_texture_input_types(
        cls,
        property_paths: list[str],
        context_name: str,
        *,
        stage: Usd.Stage | None = None,
    ) -> dict[str, Sdf.ValueTypeName]:
        """Resolve a texture batch against one stage and one metadata snapshot per shader.

        Args:
            property_paths: Shader input property paths to resolve.
            context_name: USD context containing the shaders.
            stage: Already resolved stage, or None to resolve it from ``context_name``.

        Returns:
            USD value type keyed by the requested property path.

        Raises:
            InvalidTextureInputError: If any path is not a supported shader input.
            RuntimeError: If the stage or shader registry is unavailable.
        """
        resolved_stage = stage or omni.usd.get_context(context_name).get_stage()
        if resolved_stage is None:
            raise RuntimeError(f"No USD stage is open for context '{context_name}'")
        shader_inputs_by_prim: dict[Sdf.Path, tuple[UsdShadePropertyPlaceholder, ...]] = {}
        return {
            property_path: cls._get_texture_input_type(property_path, resolved_stage, shader_inputs_by_prim)
            for property_path in property_paths
        }

    @classmethod
    def _get_texture_input_type(
        cls,
        property_path: str,
        stage: Usd.Stage,
        shader_inputs_by_prim: dict[Sdf.Path, tuple[UsdShadePropertyPlaceholder, ...]],
    ) -> Sdf.ValueTypeName:
        """Resolve one input using caller-owned stable stage and shader metadata.

        Args:
            property_path: Shader input property path to resolve.
            stage: Stable USD stage for the complete validation batch.
            shader_inputs_by_prim: Cached shader metadata keyed by prim path.

        Returns:
            The input's Asset or String USD value type.

        Raises:
            InvalidTextureInputError: If the path, shader, or texture input is invalid.
            RuntimeError: If shader metadata cannot be read.
        """
        if not isinstance(property_path, str) or not Sdf.Path.IsValidPathString(property_path):
            raise InvalidTextureInputError(f"The string is not a valid path: {property_path}")

        path = Sdf.Path(property_path)
        if not path.IsPropertyPath():
            raise InvalidTextureInputError(
                f"The property path does not point to a valid USD shader input: {property_path}"
            )

        prim_path = path.GetPrimPath()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim:
            raise InvalidTextureInputError(f"The prim path does not exist in the current stage: {prim_path}")
        if not prim.IsA(UsdShade.Shader):
            raise InvalidTextureInputError(
                f"The property path does not point to a valid USD shader property: {property_path}"
            )
        if not path.name.startswith("inputs:"):
            raise InvalidTextureInputError(
                f"The property path does not point to a valid USD shader input: {property_path}"
            )

        authored_attribute = prim.GetAttribute(path.name)
        if authored_attribute:
            authored_type = authored_attribute.GetTypeName()
            if (
                not UsdShade.Input.IsInput(authored_attribute)
                or str(authored_type) not in VALID_TEXTURE_INPUT_TYPE_NAMES
            ):
                raise InvalidTextureInputError(
                    f"The property path does not point to a valid USD shader input: {property_path}"
                )
            return authored_type

        if prim_path not in shader_inputs_by_prim:
            try:
                shader_inputs_by_prim[prim_path] = tuple(ShaderInfoAPI(prim).get_input_properties())
            except Tf.ErrorException as error:
                raise RuntimeError(f"Could not read shader input metadata for: {property_path}") from error

        for input_property in shader_inputs_by_prim[prim_path]:
            input_type = Sdf.ValueTypeNames.Find(str(input_property.GetTypeName()))
            if input_property.GetName() == path.name and str(input_type) in VALID_TEXTURE_INPUT_TYPE_NAMES:
                return input_type

        raise InvalidTextureInputError(f"The property path does not point to a valid USD shader input: {property_path}")

    @classmethod
    def is_valid_texture_prim(
        cls,
        texture_tuple: tuple[str | None, str | Path | None],
        context_name: str,
        *,
        stage: Usd.Stage | None = None,
    ):
        """Validate that a texture property identifies an Asset or String shader input.

        Args:
            texture_tuple: Texture property path paired with its replacement asset path.
            context_name: USD context containing the texture property.
            stage: Already resolved stage, or None to resolve it from ``context_name``.

        Returns:
            The unchanged texture tuple after successful validation.

        Raises:
            InvalidTextureInputError: If the property path is invalid, missing, not a shader input, or has an
                unsupported value type.
            RuntimeError: If the stage or shader registry is unavailable.
        """
        property_path, _ = texture_tuple
        cls.get_texture_input_type(property_path, context_name, stage=stage)
        return texture_tuple

    @classmethod
    def is_valid_texture_asset(cls, texture_tuple: tuple[str | None, str | Path | None], force: bool):
        """Validate that a replacement asset is supported, available, and eligible.

        Args:
            texture_tuple: Texture property path paired with its replacement asset path, or None for removal.
            force: Whether to bypass source availability and ingestion checks for a previously authored path.

        Returns:
            The unchanged texture tuple after successful validation.

        Raises:
            ValueError: If the asset is missing, unsupported, or not ingested when force is False.
        """
        _, asset_path = texture_tuple

        if asset_path is None:
            return texture_tuple

        asset_url = OmniUrl(asset_path)

        if asset_url.suffix.lower() not in SUPPORTED_TEXTURE_EXTENSIONS:
            raise ValueError(f"The asset path points to an unsupported texture file type: {asset_path}")

        if not force:
            if not asset_url.exists:
                raise ValueError(f"The asset path does not point to an existing file: {asset_path}")
            if not is_asset_ingested(str(asset_url)):
                raise ValueError(
                    f"The asset was not ingested. Ingest the asset before replacing the texture: {asset_path}"
                )

        return texture_tuple

    @classmethod
    def layer_is_in_project(cls, layer_id: Path | None, context_name: str):
        """Validate that a layer belongs to the current project's layer stack.

        Args:
            layer_id: Layer identifier to validate, or None when no layer filter is requested.
            context_name: USD context containing the project.

        Returns:
            The unchanged layer identifier.

        Raises:
            ValueError: If the layer does not exist or is not part of the project.
        """
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
