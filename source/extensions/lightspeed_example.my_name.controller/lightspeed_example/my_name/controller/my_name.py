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

from lightspeed_example.my_name.core import create_core
from lightspeed_example.my_name.menu import create_menu
from lightspeed_example.my_name.window import create_window


class MyName:
    def __init__(self):
        self.__default_attr = {
            "_core": None,
            "_window_setup": None,
            "_menu_setup": None,
            "_subscribe_button1_clicked": None,
            "_subscribe_button2_clicked": None,
            "_subscribe_menu1_clicked": None,
            "_subscribe_menu2_clicked": None,
        }
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)

        self._core = create_core()

        self.__create_ui()
        self.__create_menu()

    def __create_ui(self):
        """Create the main UI"""
        self._window_setup = create_window()
        self._subscribe_button1_clicked = self._window_setup.widget.subscribe_button1_clicked(self._on_button1_clicked)
        self._subscribe_button2_clicked = self._window_setup.widget.subscribe_button2_clicked(self._on_button2_clicked)

    def _on_button1_clicked(self):
        self._core.print_hello_1()

    def _on_button2_clicked(self):
        self._core.print_hello_2()

    def __create_menu(self):
        self._menu_setup = create_menu()
        self._subscribe_menu1_clicked = self._menu_setup.subscribe_menu1_clicked(self._on_menu1_clicked)
        self._subscribe_menu2_clicked = self._menu_setup.subscribe_menu2_clicked(self._on_menu2_clicked)

    def _on_menu1_clicked(self):
        self._toggle_window()

    def _on_menu2_clicked(self):
        print("menu2 clicked!")

    def _toggle_window(self):
        if self._window_setup.window:
            self._window_setup.window.visible = not self._window_setup.window.visible

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
