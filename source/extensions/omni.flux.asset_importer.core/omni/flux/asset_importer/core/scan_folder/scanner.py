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

from collections.abc import Callable
from pathlib import Path
import re

from ..data_models.constants import SUPPORTED_ASSET_EXTENSIONS, SUPPORTED_TEXTURE_EXTENSIONS


class ScannerCore:
    """Find supported asset and texture files and dispatch selected paths."""

    _VALID_EXTENSIONS = frozenset(
        extension.lower() for extension in (*SUPPORTED_ASSET_EXTENSIONS, *SUPPORTED_TEXTURE_EXTENSIONS)
    )

    def __init__(self, callbacks: dict[str, list[Callable[[list[str]], None]]]):
        """Initialize the scanner with callbacks grouped by action.

        Args:
            callbacks: Lists of callbacks keyed by the action that dispatches them.
        """
        self._callbacks = callbacks

    def add_callback(self, callback: dict[str, list[Callable[[list[str]], None]]]) -> None:
        """Add callbacks for scanner actions.

        Args:
            callback: Additional callback lists keyed by scanner action.
        """
        for key, value in callback.items():
            if key in self._callbacks:
                self._callbacks[key].extend(value)
            else:
                self._callbacks[key] = value

    def do(self, action_type: str, paths: list[str]) -> None:
        """Dispatch selected paths to the callbacks for an action.

        Args:
            action_type: Registered action whose callbacks should run.
            paths: Selected paths passed unchanged to each callback.

        Raises:
            KeyError: If no callbacks are registered for the action.
        """
        for callback in self._callbacks[action_type]:
            callback(paths)

    def get_valid_files(self, folder: Path, search_term: str) -> list[Path]:
        """Find supported files whose names match a regular expression.

        Args:
            folder: Directory whose immediate files should be scanned.
            search_term: Case-insensitive regular expression matched against each file name.

        Returns:
            Matching files in the directory's iteration order.

        Raises:
            re.error: If the search term is not a valid regular expression.
            OSError: If the directory cannot be enumerated.
        """
        search_exp = re.compile(search_term, re.IGNORECASE)
        found = []
        for file in folder.iterdir():
            if not file.is_file():
                continue
            suffix = file.suffix
            if suffix.lower() not in self._VALID_EXTENSIONS:
                continue
            if not search_exp.search(str(file.name)):
                continue
            found.append(file)
        return found
