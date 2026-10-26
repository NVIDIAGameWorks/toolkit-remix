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

__all__ = ["write_ingestion_metadata"]

from omni.flux.utils.common import path_utils
from omni.flux.validator.factory import BASE_HASH_KEY, VALIDATION_EXTENSIONS, VALIDATION_PASSED


def write_ingestion_metadata(path: str) -> None:
    """Write the sidecar that marks a generated file as ingested.

    Args:
        path: Path of the generated file.

    Raises:
        RuntimeError: If the file cannot be hashed.
    """
    file_hash = path_utils.hash_file(path)
    if file_hash is None:
        raise RuntimeError(f"The file {path} could not be hashed.")
    path_utils.write_metadata(path, BASE_HASH_KEY, file_hash)
    path_utils.write_metadata(path, VALIDATION_PASSED, True)
    path_utils.write_metadata(path, VALIDATION_EXTENSIONS, [])
