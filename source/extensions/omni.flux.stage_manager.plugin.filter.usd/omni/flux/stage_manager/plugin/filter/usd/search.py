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

from typing import Any

from .base import StageManagerUSDFilterPlugin as _StageManagerUSDFilterPlugin


class SearchPlugin(_StageManagerUSDFilterPlugin):
    display_name: str = "Search"
    tooltip: str = "Search through the list of prims"

    def filter_items(self, items: list[Any]) -> list[Any]:
        # TODO Implement the logic for the search filter
        pass

    def build_ui(self):  # noqa PLW0221
        # TODO Implement the UI for the search filter
        pass
