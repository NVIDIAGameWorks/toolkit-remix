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
import time
from source.extensions.hpc_pipeline_config.commands import HPCPipelineConfigCommands

class TestHPCPipelinePerformance(unittest.TestCase):
    def setUp(self):
        self.hpc_commands = HPCPipelineConfigCommands()

    def test_performance_configure_hpc_pipeline(self):
        config_options = {
            "option1": "value1",
            "option2": "value2"
        }
        start_time = time.time()
        self.hpc_commands.configure_hpc_pipeline(config_options)
        end_time = time.time()
        duration = end_time - start_time
        self.assertLess(duration, 1, "Configuration took too long")

    def test_performance_undo_redo(self):
        config_options = {
            "option1": "value1",
            "option2": "value2"
        }
        self.hpc_commands.configure_hpc_pipeline(config_options)

        start_time = time.time()
        self.hpc_commands.undo()
        end_time = time.time()
        duration = end_time - start_time
        self.assertLess(duration, 1, "Undo took too long")

        start_time = time.time()
        self.hpc_commands.redo()
        end_time = time.time()
        duration = end_time - start_time
        self.assertLess(duration, 1, "Redo took too long")

if __name__ == "__main__":
    unittest.main()
