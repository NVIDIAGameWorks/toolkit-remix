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

import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .model import FooterModel as _FooterModel


class FooterWidget:
    def __init__(
        self,
        model: type[_FooterModel] = None,
        height: ui.Length = None,
        column_width: ui.Length = None,
        between_columns_width: ui.Length = None,
    ):
        """
        Create a footer widget

        Args:
            model: the model that constraint the data
            height: the height of the footer
            column_width: the width of the columns of the footer
            between_columns_width: the width between each columns

        Returns:
            The footer object
        """

        self._default_attr = {"_content": None, "_model": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._model = _FooterModel() if model is None else model()
        self.__main_height = height
        self.__between_columns_width = between_columns_width or ui.Pixel(64)
        self.__column_width = column_width or ui.Pixel(480)
        self.__create_ui()

    def __create_ui(self):
        if self.__main_height is not None:
            zstack = ui.ZStack(height=self.__main_height)
        else:
            zstack = ui.ZStack()
        self._content = self._model.content()
        with zstack:
            ui.Rectangle(name="FooterBackground")
            with ui.HStack():
                ui.Spacer()
                for i in range(len(list(self._content.keys()))):
                    vstack = ui.VStack(width=self.__column_width)
                    if i in self._content:
                        with vstack:
                            for content in self._content[i]:
                                content()

                    if i != len(list(self._content.keys())) - 1:
                        ui.Spacer(width=self.__between_columns_width)
                ui.Spacer()

    def destroy(self):
        _reset_default_attrs(self)
