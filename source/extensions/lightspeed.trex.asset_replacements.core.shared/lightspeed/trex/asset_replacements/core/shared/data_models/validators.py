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

__all__ = ["AssetReplacementsValidators"]

import re
from pathlib import Path

import omni.usd
from lightspeed.common import constants
from lightspeed.trex.utils.common.asset_utils import is_asset_ingested
from lightspeed.trex.utils.common.prim_utils import is_material_prototype
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS as _SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.utils.common import path_utils
from omni.flux.utils.common.omni_url import OmniUrl
from pxr import Sdf, Usd

from .enums import ReplacementAssetType

_MDL_EXTENSION = ".mdl"
_REPLACEMENT_EXTENSIONS_BY_TYPE = {
    ReplacementAssetType.MDL: (_MDL_EXTENSION,),
    ReplacementAssetType.MESH: tuple(constants.USD_EXTENSIONS),
    ReplacementAssetType.TEXTURE: tuple(_SUPPORTED_TEXTURE_EXTENSIONS),
}
_VALID_REPLACEMENT_EXTENSIONS = (
    *_REPLACEMENT_EXTENSIONS_BY_TYPE[ReplacementAssetType.MESH],
    *_REPLACEMENT_EXTENSIONS_BY_TYPE[ReplacementAssetType.MDL],
    *_REPLACEMENT_EXTENSIONS_BY_TYPE[ReplacementAssetType.TEXTURE],
)


class AssetReplacementsValidators:
    @classmethod
    def is_valid_prim(cls, prim_path: str, context_name: str):
        try:
            path = Sdf.Path(prim_path)
            if not path:
                raise ValueError("Invalid prim path")
        except Exception as e:
            raise ValueError(f"The string is not a valid prim path: {prim_path}") from e

        stage = omni.usd.get_context(context_name).get_stage()
        if stage is None:
            raise ValueError("No stage is currently loaded")
        if not stage.GetPrimAtPath(path):
            raise ValueError(f"The prim path does not exist in the current stage: {prim_path}")

        return prim_path

    @classmethod
    def is_valid_mesh(cls, prim_path: str):
        if not re.match(constants.REGEX_MESH_PATH, prim_path) and not re.match(constants.REGEX_IN_MESH_PATH, prim_path):
            raise ValueError(f"The prim path does not point to a model: {prim_path}")

        return prim_path

    @classmethod
    def is_valid_material(cls, prim_path: str, context_name: str):
        stage = omni.usd.get_context(context_name).get_stage()
        if stage is None:
            raise ValueError("No stage is currently loaded")
        prim = stage.GetPrimAtPath(prim_path)
        if not prim:
            raise ValueError(f"The prim path does not exist in the current stage: {prim_path}")

        if not is_material_prototype(prim):
            raise ValueError(f"The prim path does not point to a material: {prim_path}")

        return prim_path

    @classmethod
    def has_at_least_one_ref(cls, prim_path: str, context_name: str):
        stage = omni.usd.get_context(context_name).get_stage()
        if stage is None:
            raise ValueError("No stage is currently loaded")
        prim = stage.GetPrimAtPath(prim_path)

        if not prim:
            raise ValueError(f"The prim path does not exist in the current stage: {prim_path}")

        _, references = cls.get_prim_references(prim_path, context_name)

        if not references:
            raise ValueError("The selected prim has no references")

        return prim_path

    @classmethod
    def ref_exists_in_prim(cls, asset_path: Path, layer_id: Path, prim_path: str, context_name: str):
        stage = omni.usd.get_context(context_name).get_stage()
        if stage is None:
            raise ValueError("No stage is currently loaded")
        prim = stage.GetPrimAtPath(prim_path)

        if not prim:
            raise ValueError(f"The prim path does not exist in the current stage: {prim_path}")

        _, references = cls.get_prim_references(prim_path, context_name)

        for reference, layer in references:
            if (
                OmniUrl(reference.assetPath).path.lower() == OmniUrl(asset_path).path.lower()
                and OmniUrl(layer.identifier).path.lower() == OmniUrl(layer_id).path.lower()
            ):
                return prim_path

        raise ValueError(f"The reference ({asset_path}) does not exist for prim: {prim_path}")

    @classmethod
    def is_valid_file_path(cls, asset_path: Path):
        if not path_utils.is_file_path_valid(str(asset_path), log_error=False):
            raise ValueError(f"The file path is invalid: {asset_path}")
        return asset_path

    @classmethod
    def is_asset_ingested(cls, asset_path: Path):
        if not is_asset_ingested(asset_path):
            raise ValueError(
                f"The asset path is not valid. Assets must be ingested before they can be referenced: {asset_path}"
            )

        return asset_path

    @classmethod
    def get_replacement_asset_type(cls, asset_path: str) -> ReplacementAssetType:
        """Get the replacement asset type from an asset path.

        Args:
            asset_path: Asset path to classify.

        Returns:
            Replacement asset type matching the asset path extension, or ``ANY`` for unknown extensions.
        """
        suffix = OmniUrl(asset_path).suffix.lower()
        if suffix in constants.USD_EXTENSIONS:
            return ReplacementAssetType.MESH
        if suffix == _MDL_EXTENSION:
            return ReplacementAssetType.MDL
        if suffix in _SUPPORTED_TEXTURE_EXTENSIONS:
            return ReplacementAssetType.TEXTURE
        return ReplacementAssetType.ANY

    @classmethod
    def get_replacement_asset_extensions(cls, asset_type: ReplacementAssetType) -> tuple[str, ...]:
        """Get valid replacement file extensions for an asset type.

        Args:
            asset_type: Replacement asset type.

        Returns:
            Valid replacement file extensions for the asset type.
        """
        if asset_type == ReplacementAssetType.ANY:
            return _VALID_REPLACEMENT_EXTENSIONS
        return _REPLACEMENT_EXTENSIONS_BY_TYPE[asset_type]

    @classmethod
    def is_valid_replacement_asset(cls, asset_path: str, asset_type: ReplacementAssetType) -> bool:
        """Check whether an asset path is valid for a replacement asset type.

        Args:
            asset_path: Candidate replacement asset path.
            asset_type: Replacement asset type to validate against.

        Returns:
            Whether the candidate is a file with a compatible replacement extension.
        """
        replacement_asset_url = OmniUrl(asset_path)
        return (
            replacement_asset_url.is_file
            and replacement_asset_url.suffix.lower() in cls.get_replacement_asset_extensions(asset_type)
        )

    @classmethod
    def layer_is_in_project(cls, layer_id: Path | None, context_name: str):
        if layer_id is None:
            return layer_id

        layer = Sdf.Layer.FindOrOpen(str(layer_id))
        if not layer:
            raise ValueError(f"The layer does not exist: {layer_id}")

        stage = omni.usd.get_context(context_name).get_stage()
        if stage is None:
            raise ValueError("No stage is currently loaded")
        project_layer_ids = [
            _layer.identifier for _layer in stage.GetLayerStack(includeSessionLayers=False)
        ] + stage.GetMutedLayers()

        # Make sure the layer is in the currently opened project
        if layer.identifier not in project_layer_ids:
            raise ValueError(f"The layer is not present in the loaded project's layer stack: {layer_id}")

        return layer_id

    @classmethod
    def get_prim_references(
        cls,
        prim_path: str,
        context_name: str,
        *,
        stage: Usd.Stage | None = None,
        ancestor_cache: dict[Sdf.Path, tuple[Usd.Prim | None, list[tuple[Sdf.Reference, Sdf.Layer]]]] | None = None,
    ) -> tuple[Usd.Prim, list[tuple[Sdf.Reference, Sdf.Layer]]]:
        """Get the prim and references that introduce the specified asset.

        Args:
            prim_path: Path of the asset prim.
            context_name: USD context to use when no stage is supplied.
            stage: Stage to use instead of the context stage.
            ancestor_cache: Optional caller-owned cache of ancestor paths and reference results.
                This method updates the supplied dictionary. Use it for one stage only.
                Discard it when the stage or its reference composition changes.

        Returns:
            The prim that introduces the asset and its reference-layer pairs. If no reference
            is found, returns the requested prim and an empty list. An invalid path returns
            an invalid prim and an empty list. Cached reference lists are shared. Do not modify them.

        Raises:
            ValueError: If no stage is available.
        """
        if stage is None:
            stage = omni.usd.get_context(context_name).get_stage()
        if stage is None:
            raise ValueError("No stage is currently loaded")
        prim = stage.GetPrimAtPath(str(prim_path))
        if not prim:
            # Invalid prim path
            return prim, []

        introducing_prim = prim

        visited = []
        while introducing_prim:
            path = introducing_prim.GetPath()
            if ancestor_cache is not None and path in ancestor_cache:
                owner, references = ancestor_cache[path]
                for visited_path in visited:
                    ancestor_cache[visited_path] = (owner, references)
                return owner if owner is not None else prim, references
            visited.append(path)
            # An asset reference requires more than one prim in the stack.
            prim_stack = introducing_prim.GetPrimStack()
            if len(prim_stack) > 1:
                break
            introducing_prim = introducing_prim.GetParent()
        else:
            if ancestor_cache is not None:
                for path in visited:
                    ancestor_cache[path] = (None, [])
            return prim, []

        references = omni.usd.get_composed_references_from_prim(introducing_prim)

        # If no references are found, try to build a reference using the prim stack
        if not references:
            external_layers = [i.layer for i in prim_stack if i.layer not in stage.GetLayerStack()]
            if external_layers:
                reference_layer = external_layers[-1]
                introducing_layer = prim_stack[0].layer
                relative_path = str(Path(reference_layer.realPath).relative_to(Path(introducing_layer.realPath).parent))

                references = [(Sdf.Reference(relative_path), introducing_layer)]

        if ancestor_cache is not None:
            for path in visited:
                ancestor_cache[path] = (introducing_prim, references)
        return introducing_prim, references
