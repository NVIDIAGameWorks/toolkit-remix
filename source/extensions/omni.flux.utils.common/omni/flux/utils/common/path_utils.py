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

from __future__ import annotations

__all__ = [
    "ElideModes",
    "cleanup_file",
    "delete_metadata",
    "elide_path",
    "get_absolute_path_from_relative",
    "get_invalid_extensions",
    "get_new_hash",
    "get_udim_sequence",
    "hash_file",
    "hash_match_metadata",
    "is_absolute_path",
    "is_file_path_valid",
    "is_udim_texture",
    "open_file_using_os_default",
    "read_file",
    "read_json_file",
    "read_metadata",
    "texture_to_udim",
    "write_file",
    "write_json_file",
    "write_metadata",
]

import hashlib
import json
import ntpath
import os
import platform
import posixpath
import re
import subprocess
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any
from enum import Enum, auto

import carb
import carb.tokens
import omni.client
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl

if TYPE_CHECKING:
    from pxr import Sdf

_REGEX_MATCH_UDIM = re.compile("^.*(<UDIM>|<UVTILE0>|<UVTILE1>).*")
_REGEX_UDIM_GROUP_UV_TILE = re.compile("^(.*)(<UDIM>|<UVTILE0>|<UVTILE1>)(.*)")
_REGEX_UDIM_GROUP_NUMBERS = re.compile("^(.*)([0-9][0-9][0-9][0-9])(.*)")


def is_absolute_path(path: str) -> bool:
    """Check if the path is absolute or not"""
    parts = omni.client.break_url(path)
    return parts.scheme not in {None, "file"} or ntpath.isabs(parts.path) or posixpath.isabs(parts.path)


def get_absolute_path_from_relative(path: str, layer: Sdf.Layer):
    """
    Get absolute path from a relative path. If a layer is given, it will compute the absolute path from the layer

    Args:
        path: the relative path
        layer: the layer the path is relative to

    Returns:
        the absolute path
    """
    return omni.client.normalize_url(layer.ComputeAbsolutePath(path)).replace("\\", "/")


def is_file_path_valid(path: str, layer: Sdf.Layer | None = None, log_error: bool = True) -> bool:
    """
    Check if the relative path that depends on the layer is a valid path

    Args:
        path: the relative path to check
        layer: the Sdf layer that the relative path depends on
        log_error: show an error or not

    Returns:
        True if the path is valid, else False
    """
    if not path or not path.strip():
        if log_error:
            carb.log_error(f"{path} is not valid")
        return False
    if layer is not None:
        path = layer.ComputeAbsolutePath(path)
    path = omni.client.normalize_url(path).replace("\\", "/")
    _, entry = omni.client.stat(path)
    if not (entry.flags & omni.client.ItemFlags.READABLE_FILE):
        if log_error:
            carb.log_error(f"{path} can't be read")
        return False
    return True


def read_file(file_path: str) -> bytes:
    """
    Read a file on a disk (Omniverse server or regular os disk)

    Args:
        file_path: the file path to read

    Returns:
        The bytes from the data that we got from the file
    """

    result, _, content = omni.client.read_file(file_path)
    if result == omni.client.Result.OK:
        result_data = memoryview(content).tobytes()
    else:
        try:  # try local
            with open(file_path, "rb") as in_file:
                result_data = in_file.read()
        except OSError as exc:
            message = f"Cannot read {file_path}, error code: {result}."
            carb.log_error(message)
            raise OSError(message) from exc

    return result_data


def read_json_file(file_path: str) -> dict[Any, Any]:
    """
    Read a json file from Nucleus or local disk

    Args:
        file_path: the json file path to read

    Returns:
        The data from the json file
    """
    file_path = carb.tokens.get_tokens_interface().resolve(file_path)
    bytes_data = read_file(file_path)
    with BytesIO(bytes_data) as buf:
        return json.load(buf)


def write_file(file_path: str, data: bytes, raise_if_error: bool = True) -> bool:
    """
    Write a file on a disk (Omniverse server or regular os disk)

    Args:
        file_path: the json file path
        data: the data to write in the json
        raise_if_error: raise if we failed to write the file

    Returns:
        True is everything is fine
    """
    # check if we can write in the directory
    directory = os.path.dirname(file_path)
    result, stat = omni.client.stat(directory)
    if result == omni.client.Result.OK:
        is_writeable = stat.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN
        if not is_writeable:
            return False
    else:
        return False
    result = omni.client.write_file(file_path, data)
    if raise_if_error and result != omni.client.Result.OK:
        message = f"Cannot write {file_path}, error code: {result}."
        carb.log_error(message)
        raise OSError(message)
    return True


def write_json_file(file_path: str, data: dict[Any, Any], raise_if_error: bool = True) -> bool:
    """
    Write a json file on Nucleus or local disk

    Args:
        file_path: the json file path
        data: the data to write in the json
        raise_if_error: raise if we failed to write the file

    Returns:
        True is everything is fine
    """
    file_path = carb.tokens.get_tokens_interface().resolve(file_path)
    return write_file(file_path, json.dumps(data, indent=4).encode("utf-8"), raise_if_error=raise_if_error)


def get_new_hash(abs_in_path_str: str, abs_out_path_str: str, key: str = "src_hash") -> str | None:
    """
    Get the new hash of a file.
    If the input file doesn't exist, None is returned.
    If the current metadata file doesn't exist, the hash is returned.
    If the current metadata file exists but the hash in the metadata is different than the current one,
    the hash is returned.

    Args:
        abs_in_path_str: the input file
        abs_out_path_str: the output file
        key: metadata key to grab

    Returns:
        A hash or none
    """
    src_hash = hash_file(abs_in_path_str)
    if src_hash is None:
        return None
    old_src_hash = read_metadata(abs_out_path_str, key)
    if old_src_hash is None or src_hash != old_src_hash:
        return src_hash
    return None


def hash_match_metadata(file_path: str, key: str = "src_hash") -> bool | None:
    """
    Check is a hash matches the one from the metadata file

    Args:
        file_path: the input file to check
        key: metadata key to grab

    Returns:
        True is the hash of the file match the one in the metadata
    """
    src_hash = hash_file(file_path)
    if src_hash is None:
        return False
    old_src_hash = read_metadata(file_path, key)
    return not (old_src_hash is None or src_hash != old_src_hash)


def hash_file(file_path: str, block_size: int = 8192) -> str | None:
    """
    Generate a hash from the data in a file.

    Args:
        file_path: the json file path
        block_size: block size to read the file

    Returns:
        string containing the md5 hexdigest of the passed in file's contents
    """
    file_path = carb.tokens.get_tokens_interface().resolve(file_path)
    new_hash = None
    try:
        m = hashlib.md5()
        with open(file_path, "rb") as asset_file:
            while True:
                buf = asset_file.read(block_size)
                if not buf:
                    break
                m.update(buf)
        new_hash = m.hexdigest()

    except OSError:
        carb.log_error(f"Error opening asset file for hashing: {file_path}.")
    return new_hash


def delete_metadata(file_path: str, key: str):
    """
    Delete a specific metadata key from a file

    Args:
        file_path: the file path to check (not the metadata file)
        key: the key to delete

    Returns:
        None
    """
    resolved_path = Path(carb.tokens.get_tokens_interface().resolve(file_path))
    meta_file_path = resolved_path.with_suffix(resolved_path.suffix + ".meta")
    if meta_file_path.exists():
        data = read_json_file(str(meta_file_path))
        if key in data:
            del data[key]
            write_json_file(str(meta_file_path), data)


def write_metadata(file_path: str, key: str, value: Any, append: bool = False):
    """
    Write a metadata key for a file

    Args:
        file_path: the file path to write the metadata for (not the metadata file)
        key: the key to add
        value: the value of the metadata
        append: whether the value should be appended to a list or overwritten if is already exists

    Returns:
        None
    """
    resolved_path = Path(carb.tokens.get_tokens_interface().resolve(file_path))
    meta_file_path = resolved_path.with_suffix(resolved_path.suffix + ".meta")
    if meta_file_path.exists():
        data = read_json_file(str(meta_file_path))
        if append:
            if key in data:
                if isinstance(data[key], list):
                    data[key].append(value)
                else:
                    data[key] = [data[key], value]
            else:
                data[key] = [value]
        else:
            data[key] = value
        write_json_file(str(meta_file_path), data)
    else:
        write_json_file(str(meta_file_path), {key: [value]} if append else {key: value})


def read_metadata(file_path: str, key: str) -> Any | None:
    """
    Write a metadata key for a file

    Args:
        file_path: the file path to read the metadata for (not the metadata file)
        key: the key to read

    Returns:
        The value of the key
    """
    resolved_path = Path(carb.tokens.get_tokens_interface().resolve(file_path))
    meta_file_path = resolved_path.with_suffix(resolved_path.suffix + ".meta")
    if meta_file_path.exists():
        data = read_json_file(str(meta_file_path))
        if key in data:
            return data[key]
    return None


def cleanup_file(file_path: _OmniUrl | Path | str):
    """
    Cleanup/delete a file + his metadata file

    Args:
        file_path: the file to delete/cleanup
    """
    file_url = _OmniUrl(file_path)
    meta_file_url = file_url.with_suffix(file_url.suffix + ".meta")

    # Cleanup the file
    file_url.delete()

    # Cleanup the meta file if it exists
    if meta_file_url.exists:
        meta_file_url.delete()


def is_udim_texture(file_path: _OmniUrl | Path | str) -> bool:
    """
    Tell if the file path is an udim texture or not

    Args:
        file_path: the file path to check

    Returns:

    """
    file_url = _OmniUrl(file_path)
    return bool(re.match(_REGEX_MATCH_UDIM, str(file_url)))


def get_udim_sequence(file_path: _OmniUrl | Path | str) -> list[str]:
    """
    Get the list of the textures from an UDIM path

    Args:
        file_path: the file path that contains <UDIM> or <UVTILE0> or <UVTILE1>

    Returns:
        The list of UDIM textures
    """
    result = []
    if is_udim_texture(file_path):
        file_url = _OmniUrl(file_path)
        match0 = _REGEX_UDIM_GROUP_UV_TILE.match(str(file_url))
        if match0 is None:
            raise AssertionError(f"Failed to match {str(file_url)}")
        result = [
            str(file)
            for file in _OmniUrl(file_url.parent_url).iterdir()
            if (match1 := _REGEX_UDIM_GROUP_NUMBERS.match(str(file)))
            and match0.group(1) == match1.group(1)
            and match0.group(3) == match1.group(3)
            and int(match1.group(2)) >= 1001
        ]
    return result


def texture_to_udim(file_path: _OmniUrl | Path | str) -> str:
    """
    Transform an UDIM texture like toto.1001.png to the UDIM representation like toto.<UDIM>.png

    Args:
        file_path: the file path to transform

    Returns:
        The new name with the UDIM key
    """
    file_url = _OmniUrl(file_path)
    match = _REGEX_UDIM_GROUP_NUMBERS.match(str(file_url))
    if match and match.group(2) and int(match.group(2)) >= 1001:
        return _REGEX_UDIM_GROUP_NUMBERS.sub(r"\1<UDIM>\3", str(file_url))
    return str(file_url)


def open_file_using_os_default(path: str, highlight: bool = True):
    normalized_path = os.path.normpath(path)
    if platform.system() == "Darwin":  # macOS
        if highlight:
            subprocess.call(("open", "-R", normalized_path))
            return
        subprocess.call(("open", normalized_path))
    elif platform.system() == "Windows":  # Windows
        if highlight:
            subprocess.call(("explorer", "/select,", normalized_path))
            return
        subprocess.call(("explorer", normalized_path))
    else:  # linux variants
        if highlight:
            subprocess.call(("xdg-open", str(Path(normalized_path).parent)))
            return
        subprocess.call(("xdg-open", normalized_path))


def get_invalid_extensions(
    file_paths: list[_OmniUrl | Path | str], valid_extensions: list[str], case_sensitive: bool = False
) -> list[str]:
    """
    Given a list of paths and a list of valid extensions, find and return the extensions that were not valid

    Args:
        file_paths: the list of file paths to check
        valid_extensions: the list of valid file extensions
        case_sensitive: whether the validation should be case-sensitive

    Returns:
        The list of invalid extensions from the paths provided with no duplicate elements
    """
    invalid_extensions = []

    # Find invalid extensions
    if case_sensitive:
        invalid_extensions = [
            _OmniUrl(file_path).suffix for file_path in file_paths if _OmniUrl(file_path).suffix not in valid_extensions
        ]
    else:
        lowercase_valid_extensions = [extension.lower() for extension in valid_extensions]
        # Make output invalid extensions lowercase to indicate that it is case-insensitive
        invalid_extensions = [
            _OmniUrl(file_path).suffix.lower()
            for file_path in file_paths
            if _OmniUrl(file_path).suffix.lower() not in lowercase_valid_extensions
        ]

    # Make sure there are no duplicate elements and the list is ordered
    seen = set()
    return sorted([x for x in invalid_extensions if not (x in seen or seen.add(x))])


class ElideModes(Enum):
    """Determines where the ellipsis is placed when truncating a path string."""

    start = auto()
    end = auto()
    middle = auto()


def elide_path(path: str, max_length: int, elide_mode: ElideModes = ElideModes.middle) -> str:
    """
    Truncate a path string to fit within a maximum character length, inserting an ellipsis
    to indicate removed content. Useful for display in dialogs where ui.Label elided_text
    is not available.

    Args:
        path: The path string to truncate
        max_length: Maximum allowed character length for the returned string
        elide_mode: Where to place the ellipsis -- start, end, or middle of the string

    Returns:
        The original path if it fits within max_length, otherwise a truncated version
        with an ellipsis inserted at the specified position
    """
    ellipsis = "..."
    if len(path) <= max_length:
        return path

    if max_length <= len(ellipsis):
        return ellipsis[:max_length]

    keep = max_length - len(ellipsis)

    match elide_mode:
        case ElideModes.middle:
            left = keep // 2
            right = keep - left

            return path[:left] + ellipsis + path[-right:]

        case ElideModes.start:
            return ellipsis + path[-keep:]

        case ElideModes.end:
            return path[:keep] + ellipsis

    raise ValueError(f'elide mode "{elide_mode}" is not supported')
