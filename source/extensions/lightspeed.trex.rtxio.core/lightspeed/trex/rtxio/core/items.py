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

from enum import IntEnum


class RtxIoSplitSizePreset(IntEnum):
    SIZE_1_GB = 1024
    SIZE_2_GB = 2048
    SIZE_4_GB = 4096
    SIZE_8_GB = 8192
    SIZE_16_GB = 16384

    @property
    def label(self) -> str:
        return f"{self.value // 1024} GB"
