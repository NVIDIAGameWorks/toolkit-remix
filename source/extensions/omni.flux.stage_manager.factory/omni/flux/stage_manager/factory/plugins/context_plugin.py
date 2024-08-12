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

from .base import StageManagerPluginBase as _StageManagerPluginBase


class StageManagerContextPlugin(_StageManagerPluginBase, abc.ABC):
    """
    A plugin that allows setting up a context for the other Stage Manager plugins to use afterward.

    There should only ever be one context plugin active at any time.
    """

    @classmethod
    @property
    @abc.abstractmethod
    def display_name(cls) -> str:
        """
        The string to display when displaying the plugin in the UI
        """
        pass

    @abc.abstractmethod
    def setup(self):
        """
        Set up the context for the other plugins to use
        """
        pass
