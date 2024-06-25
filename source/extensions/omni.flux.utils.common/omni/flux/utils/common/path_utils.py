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

__all__ = [
    "cleanup_file",
    "delete_metadata",
    "get_absolute_path_from_relative",
    "get_new_hash",
    "get_udim_sequence",
    "hash_file",
    "hash_match_metadata",
    "is_absolute_path",
    "is_file_path_valid",
    "is_udim_texture",
    "get_invalid_extensions",
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
import typing
from io import BytesIO
from pathlib import Path
from typing import List, Optional

import carb
import carb.tokens
import omni.client
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl

if typing.TYPE_CHECKING:
    from pxr import Sdf

_REGEX_MATCH_UDIM = re.compile("^.*(<UDIM>|<UVTILE0>|<UVTILE1>).*")
_REGEX_UDIM_GROUP_UV_TILE = re.compile("^(.*)(<UDIM>|<UVTILE0>|<UVTILE1>)(.*)")
_REGEX_UDIM_GROUP_NUMBERS = re.compile("^(.*)([0-9][0-9][0-9][0-9])(.*)")


def is_absolute_path(path: str) -> bool:
    """Check if the path is absolute or not"""
    parts = omni.client.break_url(path)
    return parts.scheme not in {None, "file"} or ntpath.isabs(parts.path) or posixpath.isabs(parts.path)


def get_absolute_path_from_relative(path: str, layer: "Sdf.Layer" = None):
    """
    Get absolute path from a relative path. If a layer is given, it will compute the absolute path from the layer

    Args:
        path: the relative path
        layer: the layer the path is relative to

    Returns:
        the absolute path
    """
    return omni.client.normalize_url(layer.ComputeAbsolutePath(path)).replace("\\", "/")


def is_file_path_valid(path: str, layer: "Sdf.Layer" = None, log_error: bool = True) -> bool:
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
    if not (entry.flags & omni.client.ItemFlags.READABLE_FILE):  # noqa PLC0325
        if log_error:
            carb.log_error(f"{path} can't be read")
        return False
    return True


def read_file(file_path) -> bytes:
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
        except IOError as exc:
            message = f"Cannot read {file_path}, error code: {result}."
            carb.log_error(message)
            raise IOError(message) from exc

    return result_data


def read_json_file(file_path: str) -> typing.Dict[typing.Any, typing.Any]:
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
        raise IOError(message)
    return True


def write_json_file(file_path: str, data: typing.Dict[typing.Any, typing.Any], raise_if_error: bool = True) -> bool:
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


def get_new_hash(abs_in_path_str: str, abs_out_path_str: str, key: str = "src_hash") -> Optional[str]:
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


def hash_match_metadata(file_path: str, key: str = "src_hash") -> Optional[bool]:
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
    if old_src_hash is None or src_hash != old_src_hash:
        return False
    return True


def hash_file(file_path: str, block_size: int = 8192) -> typing.Optional[str]:
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
    file_path_p = Path(carb.tokens.get_tokens_interface().resolve(file_path))
    file_path = file_path_p.with_suffix(file_path_p.suffix + ".meta")
    if file_path.exists():
        data = read_json_file(str(file_path))
        if key in data:
            del data[key]
            write_json_file(str(file_path), data)


def write_metadata(file_path: str, key: str, value: typing.Any):
    """
    Write a metadata key for a file

    Args:
        file_path: the file path to write the metadata for (not the metadata file)
        key: the key to add
        value: the value of the metadata

    Returns:
        None
    """
    file_path_p = Path(carb.tokens.get_tokens_interface().resolve(file_path))
    file_path = file_path_p.with_suffix(file_path_p.suffix + ".meta")
    file_path_str = str(file_path)
    if file_path.exists():
        data = read_json_file(file_path_str)
        data[key] = value
        write_json_file(file_path_str, data)
    else:
        write_json_file(file_path_str, {key: value})


def read_metadata(file_path: str, key: str) -> typing.Optional[typing.Any]:
    """
    Write a metadata key for a file

    Args:
        file_path: the file path to read the metadata for (not the metadata file)
        key: the key to read

    Returns:
        The value of the key
    """
    file_path_p = Path(carb.tokens.get_tokens_interface().resolve(file_path))
    file_path = file_path_p.with_suffix(file_path_p.suffix + ".meta")
    if file_path.exists():
        data = read_json_file(str(file_path))
        if key in data:
            return data[key]
    return None


def cleanup_file(file_path: typing.Union[_OmniUrl, Path, str]):
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


def is_udim_texture(file_path: typing.Union[_OmniUrl, Path, str]) -> bool:
    """
    Tell if the file path is an udim texture or not

    Args:
        file_path: the file path to check

    Returns:

    """
    file_url = _OmniUrl(file_path)
    if re.match(_REGEX_MATCH_UDIM, str(file_url)):
        return True
    return False


def get_udim_sequence(file_path: typing.Union[_OmniUrl, Path, str]) -> List[str]:
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
        for file in _OmniUrl(file_url.parent_url).iterdir():
            match1 = _REGEX_UDIM_GROUP_NUMBERS.match(str(file))
            if (
                match1
                and match0.group(1) == match1.group(1)
                and match0.group(3) == match1.group(3)
                and int(match1.group(2)) >= 1001
            ):
                result.append(str(file))
    return result


def texture_to_udim(file_path: typing.Union[_OmniUrl, Path, str]) -> str:
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


def open_file_using_os_default(path: str):
    if platform.system() == "Darwin":  # macOS
        subprocess.call(("open", path))
    elif platform.system() == "Windows":  # Windows
        os.startfile(path)  # noqa: PLE1101
    else:  # linux variants
        subprocess.call(("xdg-open", path))


def get_invalid_extensions(
    file_paths: List[typing.Union[_OmniUrl, Path, str]], valid_extensions: List[str], case_sensitive: bool = False
) -> List[str]:
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
        for file_path in file_paths:
            if _OmniUrl(file_path).suffix not in valid_extensions:
                invalid_extensions.append(_OmniUrl(file_path).suffix)
    else:
        lowercase_valid_extensions = [extension.lower() for extension in valid_extensions]
        for file_path in file_paths:
            if _OmniUrl(file_path).suffix.lower() not in lowercase_valid_extensions:
                # Make output invalid extensions lowercase to indicate that it is case-insensitive
                invalid_extensions.append(_OmniUrl(file_path).suffix.lower())

    # Make sure there are no duplicate elements and the list is ordered
    seen = set()
    unique_invalid_extensions = sorted([x for x in invalid_extensions if not (x in seen or seen.add(x))])

    return unique_invalid_extensions
