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

    def _configure_hpc_pipeline(self, config_options):
        """
        Configure the HPC pipeline with the provided options.

        Args:
            config_options (dict): A dictionary containing configuration options for the HPC pipeline.
        """
        self._hpc_config = config_options

        # Implement configuration commands with undo support
        self._undo_stack = []
        self._redo_stack = []

        for command, value in config_options.items():
            self._execute_command(command, value)

    def _execute_command(self, command, value):
        """
        Execute a configuration command and add it to the undo stack.

        Args:
            command (str): The configuration command to execute.
            value (any): The value associated with the command.
        """
        # Execute the command (this is a placeholder, replace with actual implementation)
        print(f"Executing command: {command} with value: {value}")

        # Add the command to the undo stack
        self._undo_stack.append((command, value))

    def undo(self):
        """
        Undo the last configuration command.
        """
        if self._undo_stack:
            command, value = self._undo_stack.pop()
            # Implement undo logic (this is a placeholder, replace with actual implementation)
            print(f"Undoing command: {command} with value: {value}")
            self._redo_stack.append((command, value))

    def redo(self):
        """
        Redo the last undone configuration command.
        """
        if self._redo_stack:
            command, value = self._redo_stack.pop()
            # Implement redo logic (this is a placeholder, replace with actual implementation)
            print(f"Redoing command: {command} with value: {value}")
            self._execute_command(command, value)

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
