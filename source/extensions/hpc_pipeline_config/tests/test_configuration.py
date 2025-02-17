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

import unittest
from source.extensions.hpc_pipeline_config.commands import HPCPipelineConfigCommands

class TestHPCPipelineConfig(unittest.TestCase):
    def setUp(self):
        self.hpc_commands = HPCPipelineConfigCommands()

    def test_configure_hpc_pipeline(self):
        config_options = {
            "option1": "value1",
            "option2": "value2"
        }
        self.hpc_commands.configure_hpc_pipeline(config_options)
        self.assertEqual(self.hpc_commands._hpc_config, config_options)

    def test_undo_redo(self):
        config_options = {
            "option1": "value1",
            "option2": "value2"
        }
        self.hpc_commands.configure_hpc_pipeline(config_options)
        self.hpc_commands.undo()
        self.assertEqual(len(self.hpc_commands._undo_stack), 1)
        self.assertEqual(len(self.hpc_commands._redo_stack), 1)
        self.hpc_commands.redo()
        self.assertEqual(len(self.hpc_commands._undo_stack), 1)
        self.assertEqual(len(self.hpc_commands._redo_stack), 0)

    def test_multiple_undo_redo(self):
        config_options = {
            "option1": "value1",
            "option2": "value2"
        }
        self.hpc_commands.configure_hpc_pipeline(config_options)
        self.hpc_commands.undo()
        self.hpc_commands.undo()
        self.assertEqual(len(self.hpc_commands._undo_stack), 0)
        self.assertEqual(len(self.hpc_commands._redo_stack), 2)
        self.hpc_commands.redo()
        self.hpc_commands.redo()
        self.assertEqual(len(self.hpc_commands._undo_stack), 2)
        self.assertEqual(len(self.hpc_commands._redo_stack), 0)

    def test_invalid_configuration(self):
        config_options = {
            "invalid_option": "value"
        }
        with self.assertRaises(ValueError):
            self.hpc_commands.configure_hpc_pipeline(config_options)

    def test_partial_configuration(self):
        config_options = {
            "option1": "value1"
        }
        self.hpc_commands.configure_hpc_pipeline(config_options)
        self.assertEqual(self.hpc_commands._hpc_config, config_options)
        self.hpc_commands.undo()
        self.assertEqual(len(self.hpc_commands._undo_stack), 0)
        self.assertEqual(len(self.hpc_commands._redo_stack), 1)

if __name__ == "__main__":
    unittest.main()
