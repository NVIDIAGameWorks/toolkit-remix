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

from enum import IntEnum


class Executors(IntEnum):
    CURRENT_PROCESS_EXECUTOR = 0
    EXTERNAL_PROCESS_EXECUTOR = 1

    @classmethod
    def get_names(cls):
        formatted_names = []
        for executor in cls:
            formatted_name = " ".join(part.capitalize() for part in executor.name.split("_")[:-1])
            formatted_names.append(formatted_name)
        return formatted_names
