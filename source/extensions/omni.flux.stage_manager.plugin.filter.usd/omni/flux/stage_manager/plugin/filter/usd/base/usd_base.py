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

import abc

from omni.flux.stage_manager.factory.plugins import StageManagerFilterPlugin as _StageManagerFilterPlugin
from pydantic import PrivateAttr


class StageManagerUSDFilterPlugin(_StageManagerFilterPlugin, abc.ABC):
    # Shared UI constants for consistent alignment across all filter plugins
    _LABEL_WIDTH: int = PrivateAttr(default=140)  # Width in pixels for filter labels

    _context_name: str = PrivateAttr(default="")

    def set_context_name(self, name: str):
        """Set usd context to initialize plugin before items are rebuilt."""
        self._context_name = name
