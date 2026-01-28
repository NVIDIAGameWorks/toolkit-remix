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

from typing import List, Tuple

import omni.usd
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP as _TEXTURE_TYPE_INPUT_MAP
from omni.flux.asset_importer.core.data_models import TextureTypes as _TextureTypes
from omni.flux.asset_importer.core.utils import get_texture_sets as _get_texture_sets
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from pxr import Sdf, Tf


@omni.usd.handle_exception
async def create_prims_and_link_assets(
    context_name: str, imported_files: List[Tuple[_OmniUrl, _TextureTypes]]
) -> List[str]:
    """
    Create material(s) from a list of textures. It will setup 1 material by PBR texture set

    Args:
        context_name: the context name to use
        imported_files: the list of texture file paths + the texture types

    Returns:
        The created material paths
    """
    context = omni.usd.get_context(context_name)
    stage = context.get_stage()

    all_paths = {str(url): c for url, c in imported_files}
    texture_sets = _get_texture_sets(list(all_paths.keys()))
    grouped_textures = {}
    for mat_prefix, texture_types in texture_sets.items():
        grouped_textures[mat_prefix] = []
        for _, path in texture_types:
            str_omni_path = str(_OmniUrl(path))
            grouped_textures[mat_prefix].append((str_omni_path, all_paths[str_omni_path]))

    material_paths = []
    for mat_prefix, imported_types in grouped_textures.items():
        # Create a unique valid prim path based on the filename
        prim_path = omni.usd.get_stage_next_free_path(
            stage, f"/TextureImporter/Looks/{Tf.MakeValidIdentifier(mat_prefix)}", False
        )
        material_paths.append(prim_path)
        # Create the prim as an MDL material using an OmniPBR shader
        # We need to know the shader here, so we can populate the right properties in the next step
        omni.kit.commands.execute(
            "CreateMdlMaterialPrim",
            mtl_url="OmniPBR.mdl",
            mtl_name="OmniPBR",
            mtl_path=prim_path,
            stage=stage,
            context_name=context_name,
        )

        material_prim = stage.GetPrimAtPath(prim_path)
        material_shader_prim = omni.usd.get_shader_from_material(material_prim, get_prim=True)

        for imported_path, imported_type in imported_types:
            input_path = material_shader_prim.GetPath().AppendProperty(_TEXTURE_TYPE_INPUT_MAP.get(imported_type))

            # Populate the properties for the materials based on the texture type
            omni.kit.commands.execute(
                "ChangePropertyCommand",
                prop_path=str(input_path),
                value=Sdf.AssetPath(str(imported_path)),
                prev=None,
                type_to_create_if_not_exist=Sdf.ValueTypeNames.Asset,
                usd_context_name=context_name,
            )

            # If importing normals, make sure to define what kind of normals we are importing
            # For OmniPBR this is done by setting `flip_tangent_v` where a value of True means DirectX and False OpenGL
            # Note: we only set this property for DX/OGL normals, not for OTH as the presence of this property is what
            # triggers OTH conversion.
            if imported_type in [_TextureTypes.NORMAL_OGL, _TextureTypes.NORMAL_DX, _TextureTypes.NORMAL_OTH]:
                encoding = -1
                match imported_type:
                    case _TextureTypes.NORMAL_OTH:
                        encoding = 0  # _NormalMapEncodings.OCTAHEDRAL
                    case _TextureTypes.NORMAL_OGL:
                        encoding = 1  # _NormalMapEncodings.TANGENT_SPACE_OGL
                    case _TextureTypes.NORMAL_DX:
                        encoding = 2  # _NormalMapEncodings.TANGENT_SPACE_DX

                omni.kit.commands.execute(
                    "ChangePropertyCommand",
                    prop_path=str(material_shader_prim.GetPath().AppendProperty("inputs:encoding")),
                    value=encoding,
                    prev=None,
                    type_to_create_if_not_exist=Sdf.ValueTypeNames.Int,
                    usd_context_name=context_name,
                )
    return material_paths
