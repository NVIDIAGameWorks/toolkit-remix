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

from typing import Optional, Tuple


def color_to_hex(color: Tuple[float, float, float, Optional[float]]) -> int:
    """Convert float rgb to int"""

    def to_int(number: float) -> int:
        return int(255 * max(0.0, min(1.0, number)))

    red = to_int(color[0])
    green = to_int(color[1])
    blue = to_int(color[2])
    alpha = to_int(color[3]) if len(color) > 3 else 255
    return (alpha << 8 * 3) + (blue << 8 * 2) + (green << 8 * 1) + red


def hex_to_color(hex_value: int) -> Tuple[int, int, int, int]:
    """Convert hex to RGBA"""
    red = hex_value & 255
    green = (hex_value >> 8) & 255
    blue = (hex_value >> 16) & 255
    alpha = (hex_value >> 24) & 255
    return red, green, blue, alpha
