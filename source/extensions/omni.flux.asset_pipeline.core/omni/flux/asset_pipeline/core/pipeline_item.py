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

__all__ = ["PipelineItem"]

from dataclasses import dataclass
from typing import Generic, TypeVar

TValue = TypeVar("TValue")


@dataclass
class PipelineItem(Generic[TValue]):
    """Base typed value container for a pipeline item.

    Product-specific contract fields must live on concrete subclasses, not in
    generic metadata dictionaries. Steps may mutate this object in place, but
    must not replace it with another item type at step boundaries.
    """

    value: TValue
