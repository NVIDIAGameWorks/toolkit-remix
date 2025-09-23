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

from collections.abc import Callable, Generator
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Any

import omni.client
from pydantic_core import core_schema


class OmniUrl:
    """
    A class to present a pathlib like wrapper around omni client urls.
    """

    def __init__(self, url: str | Path | "OmniUrl", list_entry=None):
        self._url = str(url).replace("\\", "/")
        windows_path = PureWindowsPath(self._url)
        if windows_path.is_absolute():
            self._path: PurePath = windows_path
            self._parts = omni.client.break_url("")
        else:
            self._parts = omni.client.break_url(self._url)
            self._path = PurePosixPath(self._parts.path)

        self._list_entry = list_entry

    def __str__(self) -> str:
        return self._url

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: url={self._url}>"

    def __eq__(self, other: object) -> bool:
        return self._url == str(other)

    def __hash__(self) -> int:
        return hash(self.path)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: Callable[[Any], core_schema.CoreSchema]
    ) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.no_info_plain_validator_function(cls._validate_omni_url_for_pydantic),
            serialization=core_schema.to_string_ser_schema(),
        )

    @classmethod
    def _validate_omni_url_for_pydantic(cls, v: Any) -> "OmniUrl":
        if isinstance(v, OmniUrl):
            return v
        if isinstance(v, (str, Path)):
            return cls(v)
        raise TypeError(f"Invalid type for OmniUrl. Expected OmniUrl, Path, or str, got {type(v).__name__}")

    def _url_from_list_entry(self, list_entry: omni.client.ListEntry) -> OmniUrl:
        url = self / list_entry.relative_path
        return OmniUrl(url, list_entry=list_entry)

    @property
    def is_directory(self) -> bool:
        """returns True if path points to a directory."""
        result, entry = omni.client.stat(self._url)
        return bool(result == omni.client.Result.OK and entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN)

    @property
    def is_file(self) -> bool:
        """returns True if path points to a file."""
        result, entry = omni.client.stat(self._url)
        return bool(result == omni.client.Result.OK and not entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN)

    @property
    def entry(self) -> omni.client.ListEntry | None:
        """returns True if path points to a file."""
        result, entry = omni.client.stat(self._url)
        return entry if result == omni.client.Result.OK else None

    def iterdir(self) -> Generator[OmniUrl]:
        """When the path points to a directory, yield path objects of the directory contents."""
        res, file_entries = omni.client.list(self._url)
        if res != omni.client.Result.OK:
            return

        for list_entry in file_entries:
            yield self._url_from_list_entry(list_entry)

    @property
    def exists(self) -> bool:
        """return True if the file or folder exists."""
        if self._list_entry:
            return True
        res, self._list_entry = omni.client.stat(self._url)
        if res != omni.client.Result.OK:
            return False
        if self._list_entry:
            return True
        return False

    @property
    def path(self) -> str:
        return self._path.as_posix()

    @property
    def parent_url(self) -> str:
        """return the folder that contains this url"""
        return omni.client.make_url(
            scheme=self._parts.scheme,
            host=self._parts.host,
            path=str(self._path.parent.as_posix()),
        )

    @property
    def name(self) -> str:
        """The final path component, if any."""
        return self._path.name

    @property
    def stem(self) -> str:
        """The final path component, minus its suffix(s)."""
        return self._path.stem

    @property
    def suffix(self) -> str:
        """
        The final component's last suffix, if any.

        This includes the leading period. For example: '.txt'
        """
        return self._path.suffix

    @property
    def suffixes(self) -> list[str]:
        """
        A list of the path's file extensions

        This includes the leading period. For example: ['.tar', '.gz']

        """
        return self._path.suffixes

    def with_path(self, path: PurePath) -> OmniUrl:
        """Return a new url with the path changed."""
        path_str = str(path.as_posix())

        # omni.client.make_url doesn't properly handle paths without a leading '/' yet. This has been fixed in the
        # latest code, so we can delete the below when we bump the kit SDK past 104.2+release.295.529af2e4.tc
        if self._parts.host and path_str[0] != "/":
            path_str = f"/{path_str}"

        url = omni.client.make_url(
            scheme=self._parts.scheme,
            host=self._parts.host,
            path=path_str,
        )
        return OmniUrl(url)

    def with_name(self, name: str) -> OmniUrl:
        """Return a new url with the url path final component changed."""
        url = omni.client.make_url(
            scheme=self._parts.scheme,
            host=self._parts.host,
            path=str(self._path.with_name(name)),
        )
        return OmniUrl(url)

    def with_suffix(self, suffix: str) -> OmniUrl:
        """Return a url with the file full suffix changed.  If the url path
        has no suffix, add given suffix.  If the given suffix is an empty
        string, remove the suffix from the url path.
        """
        new_name = self.stem + suffix
        url = omni.client.make_url(
            scheme=self._parts.scheme,
            host=self._parts.host,
            path=str(self._path.with_name(new_name)),
        )
        return OmniUrl(url)

    def delete(self):
        """
        Delete the item and wait for the result.
        """
        return omni.client.delete(str(self._url))

    def __truediv__(self, arg) -> OmniUrl:
        new_path = self.path / PurePosixPath(arg)
        return self.with_path(new_path)
