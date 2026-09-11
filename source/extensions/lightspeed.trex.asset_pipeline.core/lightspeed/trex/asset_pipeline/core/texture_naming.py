"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from __future__ import annotations

__all__ = [
    "DDS_SUFFIX",
    "get_dds_stem_suffix",
    "get_legacy_dds_suffixes",
    "get_octahedral_stem",
    "is_octahedral_source_type",
]


from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_CONVERTED_SUFFIX_MAP, TextureTypes

# Legacy ``ConvertToOctahedral`` output naming. The plugin replaced a trailing ``_Normal`` with
# ``_OTH_Normal`` and otherwise appended ``_OTH_Normal``, keeping the source file extension.
_OCTAHEDRAL_SUFFIX = "_OTH_Normal"
_OCTAHEDRAL_REPLACE_SUFFIX = "_Normal"

# Legacy ``ConvertToDDS`` output naming: ``<stem>.<letter>.rtex.dds``. Every normal semantic shared
# the single ``n`` letter, and a semantic with no mapped letter produced ``<stem>.rtex.dds``.
DDS_SUFFIX = ".rtex.dds"

_NORMAL_TEXTURE_TYPES = (TextureTypes.NORMAL_OGL, TextureTypes.NORMAL_DX, TextureTypes.NORMAL_OTH)
_OCTAHEDRAL_SOURCE_TYPES = (TextureTypes.NORMAL_DX, TextureTypes.NORMAL_OGL)


def is_octahedral_source_type(texture_type: TextureTypes) -> bool:
    """Return whether one semantic is converted to an octahedral normal map.

    Args:
        texture_type: Texture semantic to test.

    Returns:
        True when the legacy octahedral plugin converted this semantic.
    """
    return texture_type in _OCTAHEDRAL_SOURCE_TYPES


def get_octahedral_stem(source_stem: str) -> str:
    """Return the legacy octahedral filename stem for one normal-map stem.

    Args:
        source_stem: Filename stem of the source normal map.

    Returns:
        The stem that the legacy plugin produced for the converted file.
    """
    if source_stem.endswith(_OCTAHEDRAL_SUFFIX):
        return source_stem
    if source_stem.endswith(_OCTAHEDRAL_REPLACE_SUFFIX):
        return source_stem[: -len(_OCTAHEDRAL_REPLACE_SUFFIX)] + _OCTAHEDRAL_SUFFIX
    return source_stem + _OCTAHEDRAL_SUFFIX


def get_dds_stem_suffix(texture_type: TextureTypes) -> str:
    """Return the legacy DDS stem suffix for one texture semantic.

    Args:
        texture_type: Texture semantic selecting the output letter.

    Returns:
        A dotted letter such as ``.n``, or an empty string when the semantic has no letter.
    """
    lookup_type = TextureTypes.NORMAL_OGL if texture_type in _NORMAL_TEXTURE_TYPES else texture_type
    for letter, mapped_type in TEXTURE_TYPE_CONVERTED_SUFFIX_MAP.items():
        if mapped_type is lookup_type:
            return f".{letter}"
    return ""


def get_legacy_dds_suffixes(texture_type: TextureTypes) -> str:
    """Return the full trailing suffix that a converted DDS file carries.

    Args:
        texture_type: Texture semantic selecting the output letter.

    Returns:
        A suffix such as ``.n.rtex.dds``, or ``.rtex.dds`` when the semantic has no letter.
    """
    return f"{get_dds_stem_suffix(texture_type)}{DDS_SUFFIX}"
