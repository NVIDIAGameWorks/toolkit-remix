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
from lightspeed_example.my_name.widget import create_widget


class _SetupWindow:

    WINDOW_NAME = "Window example"

    def __init__(self):
        """Window"""
        self.__default_attr = {"_window": None, "_widget": None}
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)

        self.__create_ui()

    @property
    def widget(self):
        return self._widget

    @property
    def window(self):
        return self._window

    def __create_ui(self):
        """Create the main UI"""
        self._window = ui.Window(self.WINDOW_NAME, name=self.WINDOW_NAME, width=400, height=300)
        with self._window.frame:
            self._widget = create_widget()

    def destroy(self):
        for attr, value in self.__default_attr.items():
            m_attr = getattr(self, attr)
            if isinstance(m_attr, list):
                m_attrs = m_attr
            else:
                m_attrs = [m_attr]
            for m_attr in m_attrs:
                destroy = getattr(m_attr, "destroy", None)
                if callable(destroy):
                    destroy()
                del m_attr
                setattr(self, attr, value)


def create_window():
    return _SetupWindow()
