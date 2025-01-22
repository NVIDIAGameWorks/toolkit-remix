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

import carb
import omni.ext

from .my_name import MyName

_INSTANCE = None


def get_instance():
    """Expose the created instance of the tool"""
    return _INSTANCE


class MyNameExtension(omni.ext.IExt):
    """Standard extension support class, necessary for extension management"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

    def on_startup(self, ext_id):
        global _INSTANCE
        carb.log_info("[lightspeed_example.my_name] startup")
        _INSTANCE = MyName()

    def on_shutdown(self):
        global _INSTANCE
        carb.log_info("[lightspeed_example.my_name] shutdown")
        for attr, value in self.default_attr.items():
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
        _INSTANCE.destroy()
        _INSTANCE = None

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
