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

import abc
from functools import partial
from collections.abc import Callable

import omni.ui as ui


class FooterModel:
    @abc.abstractmethod
    def content(self) -> dict[int, tuple[Callable]]:
        """
        Get the data.

        Returns:
            A dictionary with all the data.
            First int is the column number, Tuple of Callable that will create the UI
        """
        return {
            0: (),
            1: (
                partial(ui.Spacer, height=ui.Pixel(24)),
                partial(ui.Label, "line1-2", height=ui.Pixel(24)),
                partial(ui.Label, "line1-3", height=ui.Pixel(24)),
            ),
            2: (
                partial(ui.Spacer, height=ui.Pixel(24)),
                self.__example,
                partial(ui.Label, "line2-2", height=ui.Pixel(24)),
                partial(ui.Label, "line2-3", height=ui.Pixel(24)),
                partial(ui.Label, "line2-4", height=ui.Pixel(24)),
            ),
        }

    def __example(self):
        with ui.HStack(height=ui.Pixel(24)):
            ui.Label("line2-1-0")
            ui.Spacer()
            ui.Label("line2-1-1", width=0)
