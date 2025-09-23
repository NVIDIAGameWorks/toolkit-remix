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

import numpy as np


def create_gradient_1d(width: int, height: int, int1: int, int2: int, is_horizontal: bool) -> np.ndarray:
    """
    Create a 1d gradient

    Args:
        width: width of the gradient
        height: height of the gradient
        int1: start number of the gradient, like 0
        int2: end number of the gradient, like 255
        is_horizontal: horizontal or vertical gradient

    Returns:
        The 1d gradient
    """
    if is_horizontal:
        return np.tile(np.linspace(int1, int2, width, dtype=np.uint8), (height, 1))
    return np.tile(np.linspace(int1, int2, height, dtype=np.uint8), (width, 1)).T


def create_gradient(
    width: int, height: int, values1: tuple[int, ...], values2: tuple[int, ...], is_horizontal_list: tuple[bool, ...]
) -> np.ndarray:
    """
    Create a gradient (like a RGBA) of any dimension

    Args:
        width: width of the gradient
        height: height of the gradient
        values1: start values (like (0, 0, 0, 255)) of the gradient. Work with any dimension.
        values2: end values (like (255, 255, 255, 255)) of the gradient. Work with any dimension.
        is_horizontal_list: horizontal or vertical gradient (like (True, True, True, True))

    Returns:
        The gradient values
    """
    result = np.zeros((height, width, len(values1)), dtype=np.uint8)

    for i, (value1, value2, is_horizontal) in enumerate(zip(values1, values2, is_horizontal_list)):
        result[:, :, i] = create_gradient_1d(width, height, value1, value2, is_horizontal)

    return result
