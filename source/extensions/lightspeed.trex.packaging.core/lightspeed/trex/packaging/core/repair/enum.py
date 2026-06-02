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

__all__ = ["PackagingRepairAction", "PackagingRepairProgress"]

from enum import Enum


class PackagingRepairAction(Enum):
    """
    Enum for the actions that can be taken on a packaging repair request.
    """

    IGNORE = "Ignore"
    REPLACE_ASSET = "Replace Asset"
    REMOVE_REFERENCE = "Remove Reference"


class PackagingRepairProgress(Enum):
    """
    Enum for the progress phases of a packaging repair operation.
    """

    APPLYING = "applying"
    SAVING = "saving"
