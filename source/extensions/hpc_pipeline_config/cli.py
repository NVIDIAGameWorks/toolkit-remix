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

import argparse
import carb
from .commands import HPCPipelineConfigCommands

def main():
    parser = argparse.ArgumentParser(description="HPC Pipeline Configuration CLI")
    parser.add_argument("--config", type=str, help="Path to the configuration file")
    parser.add_argument("--undo", action="store_true", help="Undo the last configuration command")
    parser.add_argument("--redo", action="store_true", help="Redo the last undone configuration command")
    args = parser.parse_args()

    hpc_commands = HPCPipelineConfigCommands()

    if args.config:
        with open(args.config, "r") as config_file:
            config_options = eval(config_file.read())
            hpc_commands.configure_hpc_pipeline(config_options)

    if args.undo:
        hpc_commands.undo()

    if args.redo:
        hpc_commands.redo()

if __name__ == "__main__":
    main()
