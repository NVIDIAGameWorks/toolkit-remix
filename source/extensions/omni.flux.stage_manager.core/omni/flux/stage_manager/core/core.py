# noqa PLC0302
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

from .schema import StageManagerSchema as _StageManagerSchema


class StageManagerCore:
    """
    Core extension used to orchestrate and manage the StageManager.
    The `StageManagerCore` relies on a `StageManagerSchema` to define its internal data structure.
    """

    def test(self, schema_dict: dict):
        print("*" * 96)
        print("SchemaDict :", schema_dict)
        print("Schema     :", _StageManagerSchema(**schema_dict))
        print("*" * 96)
