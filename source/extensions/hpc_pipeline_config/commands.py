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

class HPCPipelineConfigCommands:
    """Class to handle HPC pipeline configuration commands with undo support"""

    def __init__(self):
        self._hpc_config = {}
        self._undo_stack = []
        self._redo_stack = []

    def configure_hpc_pipeline(self, config_options):
        """
        Configure the HPC pipeline with the provided options.

        Args:
            config_options (dict): A dictionary containing configuration options for the HPC pipeline.
        """
        self._hpc_config = config_options

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
