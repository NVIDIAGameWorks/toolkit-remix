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

import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from omni.flux.utils.common.omni_url import OmniUrl

from .data_models import SUPPORTED_ASSET_EXTENSIONS, SUPPORTED_TEXTURE_EXTENSIONS

__all__ = ["SelectionValidation", "classify_asset_selection", "classify_texture_selection"]

SelectionPath = str | os.PathLike[str]


@dataclass(frozen=True, slots=True)
class SelectionValidation:
    """Classified paths from one asset-ingestion selection.

    Attributes:
        valid_paths: Original non-directory paths with supported extensions.
        unsupported_paths: Non-directory paths with missing or unsupported extensions.
        directory_paths: Paths that resolve to directories.
    """

    valid_paths: tuple[SelectionPath, ...]
    unsupported_paths: tuple[OmniUrl, ...]
    directory_paths: tuple[OmniUrl, ...]

    @property
    def is_valid(self) -> bool:
        """Return whether every selected path is ingestible.

        Returns:
            True when the selection has no directories or unsupported paths.
        """
        return not self.unsupported_paths and not self.directory_paths


def _classify_selection(
    paths: Iterable[SelectionPath],
    supported_extensions: Sequence[str],
) -> SelectionValidation:
    """Classify one selection with a single metadata lookup per path.

    Args:
        paths: Candidate filesystem or Omniverse paths.
        supported_extensions: Accepted extensions, including the leading period. Matching is case-insensitive.

    Returns:
        Valid paths and the two user-facing failure groups.
    """
    supported = frozenset(extension.lower() for extension in supported_extensions)
    valid_paths = []
    unsupported_paths = []
    directory_paths = []
    for path in paths:
        url = OmniUrl(path)
        if url.is_directory:
            directory_paths.append(url)
            continue
        if url.suffix.lower() not in supported:
            unsupported_paths.append(url)
            continue
        valid_paths.append(path)
    return SelectionValidation(tuple(valid_paths), tuple(unsupported_paths), tuple(directory_paths))


def classify_asset_selection(paths: Iterable[SelectionPath]) -> SelectionValidation:
    """Classify asset paths using the importer contract.

    Args:
        paths: Candidate asset paths.

    Returns:
        Classified asset selection.
    """
    return _classify_selection(paths, SUPPORTED_ASSET_EXTENSIONS)


def classify_texture_selection(paths: Iterable[SelectionPath]) -> SelectionValidation:
    """Classify texture paths using the importer contract.

    Args:
        paths: Candidate texture paths.

    Returns:
        Classified texture selection.
    """
    return _classify_selection(paths, SUPPORTED_TEXTURE_EXTENSIONS)
