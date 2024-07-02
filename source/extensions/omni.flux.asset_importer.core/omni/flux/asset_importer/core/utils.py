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

import hashlib
import re
from collections import defaultdict
from typing import Dict, List, Tuple

from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl

from .data_models import PREFIX_TEXTURE_NO_PREFIX as _PREFIX_TEXTURE_NO_PREFIX
from .data_models import TEXTURE_TYPE_CONVERTED_SUFFIX_MAP as _TEXTURE_TYPE_CONVERTED_SUFFIX_MAP
from .data_models import TEXTURE_TYPE_REGEX_MAP as _TEXTURE_TYPE_REGEX_MAP
from .data_models import TextureTypes as _TextureTypes


def parse_texture_paths(paths_to_parse, required_ext="dds"):
    """
    From a list of paths, return a dictionary with the paths broken up by _-. or capital letter

    Args:
        paths_to_parse: the texture paths
        required_ext: the texture extension

    Returns:
        dictionary of parsed textures
    """
    parsed_paths = {}
    for path in paths_to_parse:
        if not path.endswith(required_ext):
            continue
        # Split the string at underscores or periods
        parts = re.split(r"_|\.|\s|-", path)
        # Initialize an empty list to hold the final parts of the string
        parsed_parts = []

        # Iterate over each part split by underscore
        for part in parts:
            if part == required_ext:
                continue
            # Further split each part by capital letters, but keep the capital letters as part of the next word
            sub_parts = re.split("(?<=[a-z])(?=[A-Z])", part)
            parsed_parts.extend(sub_parts)
        parsed_paths[path] = parsed_parts
    return parsed_paths


def _get_default_prefix(path):
    # only 8 digit
    hash_int = int(hashlib.sha256(str(_OmniUrl(path).parent_url).encode("utf-8")).hexdigest(), 16) % 10**8
    return f"{_PREFIX_TEXTURE_NO_PREFIX}_{hash_int}"


def get_texture_sets(paths: List[str]) -> Dict[str, List[Tuple[str, str]]]:
    """
    From a list of paths, return a list of set of textures

    Args:
        paths: the texture paths

    Returns:
        Set of textures
    """
    texture_sets = defaultdict(list)

    # Combine all the TextureTypes in 1 regex expression to make building texture sets faster
    patterns = [r for r in _TEXTURE_TYPE_REGEX_MAP.values() if r is not None]
    regex_search = re.compile(rf".*({'|'.join(patterns)})", re.IGNORECASE)

    # Build Texture Sets
    for path in paths:
        file_path = _OmniUrl(path).path
        regex_match = re.search(regex_search, file_path)
        # At least 1 keyword was found
        if regex_match:
            # If the individual item expressions have matching group, use those
            match_index = 1
            for index, group in enumerate(regex_match.groups()):
                if not group:
                    continue
                match_index = index + 1
            # The possible texture type
            match_group = regex_match.group(match_index)
            # Isolate the prefix used for the texture set
            prefix = file_path[: regex_match.start(match_index)]
            # if the texture name is Albedo.png/Metal.png/... with no prefix, we hash the full parent directory path
            prefix = prefix or _get_default_prefix(path)
            texture_sets[prefix].append((match_group, path))
        else:
            if file_path not in texture_sets:
                texture_sets[file_path] = []
            texture_sets[file_path].append(("Other", path))

    return texture_sets


def determine_ideal_types(paths: List[str], pref_normal_conv: _TextureTypes = None) -> Dict[str, _TextureTypes]:
    """
    Will try to determine the TextureType based on the filename. If no TextureType can be found, no entry will be
    added to the returned dictionary.
    """

    texture_types = {}

    texture_sets = get_texture_sets(paths)

    # Sort the sets by length so the more precise prefixes overwrite the less precise prefixes
    ordered_sets = sorted(texture_sets.keys(), key=len)

    # Find the Texture Types
    for set_prefix in ordered_sets:
        set_types = texture_sets[set_prefix]

        for path in paths:
            file_path = _OmniUrl(path).path

            # Make sure the file is part of the texture set
            if not file_path.startswith(set_prefix) and not set_prefix.startswith(_PREFIX_TEXTURE_NO_PREFIX):
                continue

            texture_type = None

            # Get the texture type of the file in the set
            set_texture_type = None
            for set_type, _ in set_types:
                if file_path.startswith(set_prefix + set_type) or (
                    set_prefix.startswith(_PREFIX_TEXTURE_NO_PREFIX) and file_path.startswith(set_type)
                ):
                    set_texture_type = set_type
                    break

            # Get the enum value matching the texture type
            # If the texture type is in the set multiple times, we keep the type as OTHER since it's probably
            # not the texture type (Example: T_Metal_01.png and T_Metal_02.png)
            if set_texture_type and len([t for t, _ in set_types if t.lower() == set_texture_type.lower()]) == 1:
                for ttype in _TextureTypes:
                    pattern = _TEXTURE_TYPE_REGEX_MAP.get(ttype)
                    if pattern is None:
                        continue
                    # If the enum REGEX matches with the set texture type, we found the right type
                    if re.search(pattern, set_texture_type, re.IGNORECASE):
                        texture_type = ttype
                        break

            # Only update the texture type if a type was found.
            # Since the prefixes are ordered by length, a more precise prefix will override a broader one
            # (Example: T_Metal_Normal_OTH.png -> [T_Metal_, T_Metal_Normal_] will end up with value: OTH)
            if texture_type:
                # Special check for normals, which can be in one of three encodings
                if pref_normal_conv is not None and texture_type in [
                    _TextureTypes.NORMAL_OGL,
                    _TextureTypes.NORMAL_DX,
                    _TextureTypes.NORMAL_OTH,
                ]:
                    texture_types[path] = pref_normal_conv
                else:
                    texture_types[path] = texture_type

    # Return the list of explicitly known texture types only
    return texture_types


def get_texture_type_from_filename(filename: str) -> _TextureTypes | None:
    for tag, texture_type in _TEXTURE_TYPE_CONVERTED_SUFFIX_MAP.items():
        suffix = f"{tag}.rtex.dds"
        if filename.endswith(suffix):
            return texture_type
    return None
