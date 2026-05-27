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

__doc__ = "Shared type aliases for Flux utility consumers."

from typing import Protocol, TypeAlias

__all__ = ["RealNumber", "ScalarSequence", "ScalarValue"]

# NOTE:
# Keep ``typing.TypeAlias`` while this repo targets Python 3.10 (cp310).
# Migrate to PEP 695 ``type`` aliases when minimum Python >= 3.12.
RealNumber: TypeAlias = int | float


class ScalarSequence(Protocol):
    """Indexable per-channel scalar payload."""

    def __getitem__(self, index: int) -> RealNumber: ...


ScalarValue: TypeAlias = RealNumber | ScalarSequence
